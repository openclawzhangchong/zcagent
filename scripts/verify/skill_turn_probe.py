"""End-to-end proof that a skill installed mid-conversation reaches the model.

The unit tests show what the code does; only a real turn against a real model
shows what the model sees. This boots its own scratch control plane (own
``OCTOP_HOME``, spare port), opens one conversation, and installs a skill while
that conversation is already open -- the exact thing the plugin market does.

The canary is built so the two channels cannot be confused:

* the frontmatter ``description`` (which is the only part the system prompt
  carries) holds ``PROMPT-<rand>``;
* the SKILL.md body (reachable only by reading the file) holds ``BODY-<rand>``.

An answer containing PROMPT- proves prompt injection. An answer containing BODY-
means the model opened the file instead, which makes that run inconclusive
rather than a pass.

    python scripts/verify/skill_turn_probe.py --python .venv/Scripts/python.exe

``--provider-file`` must point at a JSON blob with base_url / api_key / model;
it is read from disk and never printed.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "verify"))

import layout_probe as lp  # noqa: E402

# Scratch-only: the setup endpoint enforces a digit + symbol password policy,
# and this control plane is thrown away at the end of the run.
ADMIN_PASSWORD = "Probe!" + secrets.token_hex(4)


def pick_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def provision(base: str, provider: dict[str, Any]) -> str:
    """Walk setup, attach the real provider, finish, and return an admin token."""
    status = lp.api(base, "GET", "/api/setup/status")
    if not status.get("setup_required"):
        raise SystemExit("scratch home is not greenfield -- refusing to reuse it")
    token = lp.api(base, "POST", "/api/setup/begin", {})["wizard_token"]
    lp.api(base, "POST", "/api/setup/database", {"driver": "sqlite", "sqlite_path": None}, token=token)
    lp.api(
        base,
        "POST",
        "/api/setup/initial-admin",
        {"username": "admin", "password": ADMIN_PASSWORD, "display_name": "探针", "locale": "zh"},
        token=token,
    )
    access = lp.api(base, "POST", "/api/auth/login", {"username": "admin", "password": ADMIN_PASSWORD})[
        "access_token"
    ]
    lp.api(
        base,
        "POST",
        "/api/admin/providers",
        {
            "name": "probe-real",
            "kind": "openai",
            "base_url": provider["base_url"],
            "api_key": provider["api_key"],
            "models": [{"id": provider["model"], "name": provider["model"], "enabled": True}],
        },
        token=access,
    )
    lp.api(base, "POST", "/api/setup/finish", {}, token=token)
    return access


def wait_running_agent(base: str, token: str, timeout_s: int = 150) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rows = lp.api(base, "GET", "/api/agents", token=token)
        rows = rows if isinstance(rows, list) else (rows.get("agents") or rows.get("items") or [])
        for r in rows:
            if str(r.get("state")) == "running":
                return str(r.get("agent_id") or r.get("id"))
        time.sleep(2)
    raise SystemExit("no agent reached state=running")


def cli(python: str, home: Path, *args: str, timeout_s: int = 300) -> str:
    env = os.environ.copy()
    env["OCTOP_HOME"] = str(home)
    env["OCTOP_DATABASE_SQLITE_PATH"] = str(home / "octop.db")
    env["OCTOP_REQUIRE_SETUP_PASSWORD"] = "0"
    env["OCTOP_KNOWLEDGE_MODEL_PREFETCH"] = "off"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [python, "-m", "octop", *args],
            env=env,
            cwd=str(ROOT),
            capture_output=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"octop {args[0]} {args[1] if len(args) > 1 else ''} timed out after {timeout_s}s") from exc
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")
        raise SystemExit(f"octop {' '.join(args[:2])} failed ({proc.returncode}): {err[-600:]}")
    return out


def create_thread(python: str, home: Path, agent_id: str) -> str:
    """Open a conversation the same way ``/new`` does; ``chats send`` refuses
    a thread id it has never seen."""
    out = cli(python, home, "chats", "create", "--agent", agent_id)
    found = re.findall(r"thr_[0-9A-Z]+", out)
    if not found:
        raise SystemExit(f"chats create returned no thread id: {out[:400]}")
    return found[0]


def run_turn(python: str, home: Path, agent_id: str, thread_id: str, prompt: str, timeout_s: int) -> str:
    return cli(
        python,
        home,
        "chats",
        "send",
        prompt,
        "--agent",
        agent_id,
        "--thread-id",
        thread_id,
        "--plain",
        timeout_s=timeout_s,
    )


def install_canary(skills_dir: Path, slug: str, prompt_secret: str, body_secret: str) -> Path:
    d = skills_dir / slug
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {slug}\n"
        f"description: 探针技能，只在系统提示词里出现口令 {prompt_secret}。\n"
        "---\n\n"
        f"# {slug}\n\n正文口令是 {body_secret}，只有真正读取本文件才能得到它。\n",
        encoding="utf-8",
    )
    return d


def point_backend_at_scratch_drive(home: Path) -> str:
    """Retarget every agent's filesystem jail at the drive this scratch home uses.

    A freshly created expert gets ``backend.root_dir = <system drive>:/``, which
    is right for the default ``%USERPROFILE%\\.octop`` but not for a scratch home
    on another drive: every ``read_file``/``execute`` then fails with "path
    outside the storage root", and a broken fixture reads exactly like a product
    failure.
    """
    import sqlite3

    drive = home.resolve().drive + "/"
    conn = None
    # The provisioning server was just killed, so its WAL/shared-memory handles
    # may still be in flight; Windows surfaces that as a transient disk I/O error.
    for attempt in range(10):
        try:
            conn = sqlite3.connect(home / "octop.db", timeout=10)
            conn.execute("select count(*) from agents").fetchone()
            break
        except sqlite3.OperationalError:
            if conn is not None:
                conn.close()
            conn = None
            if attempt == 9:
                raise
            time.sleep(2.0)
    try:
        for agent_id, raw in conn.execute("select agent_id, config_json from agents").fetchall():
            cfg = json.loads(raw or "{}")
            backend = cfg.get("backend") or {}
            if backend.get("root_dir") == drive:
                continue
            backend["root_dir"] = drive
            cfg["backend"] = backend
            conn.execute(
                "update agents set config_json = ? where agent_id = ?",
                (json.dumps(cfg, ensure_ascii=False), agent_id),
            )
        conn.commit()
    finally:
        conn.close()
    return drive


def checkpoint_channel(home: Path, agent_id: str, thread_id: str) -> dict[str, Any]:
    """Newest checkpoint's channel values for a thread, via the product's codec."""
    import sqlite3

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    db = home / "agents" / agent_id / ".octop" / "memory.sqlite"
    if not db.exists():
        return {}
    base = JsonPlusSerializer()
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "select type, checkpoint from checkpoints where thread_id=? order by checkpoint_id desc limit 1",
            (thread_id,),
        ).fetchone()
        if row is None:
            return {}
        ctype, blob = row
        if ctype != "harness-checkpoint-v1":
            ck = base.loads_typed((ctype, blob))
        else:
            size = struct.unpack(">I", blob[:4])[0]
            header = json.loads(blob[4 : 4 + size])
            ck = base.loads_typed((header["type"], blob[4 + size :]))
            for channel, digest in header["refs"].items():
                found = conn.execute("select type, value from hm_checkpoint_blobs where digest=?", (digest,)).fetchone()
                if found is not None:
                    ck["channel_values"][channel] = base.loads_typed(found)
        return ck.get("channel_values") or {}
    finally:
        conn.close()


def checkpoint_skill_names(home: Path, agent_id: str, thread_id: str) -> list[str]:
    """The pool the conversation is actually carrying, not what the UI claims."""
    return sorted(str(s["name"]) for s in checkpoint_channel(home, agent_id, thread_id).get("skills_metadata") or [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--home", type=Path, default=ROOT / ".zc-verify" / "skill-turn" / "home")
    ap.add_argument("--provider-file", type=Path, default=ROOT / ".zc-verify" / "provider-copy.json")
    ap.add_argument("--expect", choices=["fixed", "broken"], default="fixed")
    ap.add_argument("--turn-timeout", type=int, default=420)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument(
        "--reuse",
        action="store_true",
        help="skip provisioning and use the agent already on this scratch home",
    )
    args = ap.parse_args()

    provider = json.loads(args.provider_file.read_text(encoding="utf-8"))
    print(f"provider: {provider['base_url']} model={provider['model']} key_len={len(str(provider['api_key']))}")

    home = args.home
    if not args.reuse:
        if home.exists() and any(home.iterdir()):
            raise SystemExit(f"{home} is not empty; delete it, pass --reuse, or pick another --home")
        home.mkdir(parents=True)

    results: list[tuple[str, bool, str]] = []
    if args.reuse:
        rows = [p for p in (home / "agents").iterdir() if p.is_dir()] if (home / "agents").exists() else []
        if not rows:
            raise SystemExit(f"--reuse found no agent workspace under {home}")
        agent_id = rows[0].name
        print(f"reusing scratch agent {agent_id} on {home}")
    else:
        port = pick_port()
        base = f"http://127.0.0.1:{port}"
        server = lp.boot(args.python, home, port)
        try:
            access = provision(base, provider)
            agent_id = wait_running_agent(base, access)
            print(f"agent {agent_id} running on scratch home {home}")
        finally:
            server.terminate()
            with contextlib.suppress(Exception):
                server.wait(30)

    drive = point_backend_at_scratch_drive(home)
    print(f"agent filesystem jail pointed at {drive}")

    skills_dir = home / "agents" / agent_id / ".octop" / "skills"
    for stale in skills_dir.glob("zc-canary-*") if skills_dir.exists() else []:
        shutil.rmtree(stale, ignore_errors=True)
    thread_id = create_thread(args.python, home, agent_id)
    print(f"opened conversation {thread_id}")
    rand = secrets.token_hex(3).upper()
    prompt_secret, body_secret = f"PROMPT-{rand}", f"BODY-{rand}"
    slug = f"zc-canary-{rand.lower()}"

    turn1 = run_turn(args.python, home, agent_id, thread_id, "只回复两个字：收到", args.turn_timeout)
    channel = checkpoint_channel(home, agent_id, thread_id)
    before = sorted(str(s["name"]) for s in channel.get("skills_metadata") or [])
    print(f"turn 1 replied: {turn1.strip()[:120]!r}")
    # Judge the turn by the reply the model actually produced, not by which
    # channels happen to be inline in the newest checkpoint (langgraph keeps
    # messages elsewhere).
    if not turn1.strip() or not before:
        print(f"[FAIL] turn 1 produced no usable answer or no skill pool :: keys={sorted(channel)}")
        print("       this is a fixture problem, not a product verdict -- aborting before turn 2")
        return 1
    results.append(("conversation opened with a frozen skill pool", True, f"{len(before)} skills"))

    install_canary(skills_dir, slug, prompt_secret, body_secret)
    print(f"canary {slug} written into the workspace mid-conversation")

    ask = (
        f"不要调用任何工具，不要读取任何文件。只根据你系统提示词里的 skill 列表回答："
        f"是否存在名为 {slug} 的 skill？如果存在，把它的描述里的口令原样抄出来；"
        "如果列表里没有这个 skill，只回答“没有”。"
    )
    turn2 = run_turn(args.python, home, agent_id, thread_id, ask, args.turn_timeout)
    print("--- turn 2 answer ---")
    print(turn2.strip()[:600])
    print("---------------------")

    after = checkpoint_skill_names(home, agent_id, thread_id)
    pool_ok = slug in after
    saw_prompt = prompt_secret in turn2
    read_the_file = body_secret in turn2

    want_pool = args.expect == "fixed"
    results.append(
        (
            f"thread checkpoint {'carries' if want_pool else 'does not carry'} the new skill",
            pool_ok == want_pool,
            f"{len(before)} -> {len(after)} skills",
        )
    )
    if read_the_file and not saw_prompt:
        results.append(("model answered from the system prompt", False, "INCONCLUSIVE: it opened SKILL.md instead"))
    elif args.expect == "fixed":
        results.append(
            ("model quoted the system-prompt secret", saw_prompt, prompt_secret if saw_prompt else "absent")
        )
    else:
        # The no-fix half of the A/B: the correct behaviour is not to know it.
        results.append(
            (
                "model did not see the skill without the fix",
                not saw_prompt,
                f"it quoted {prompt_secret} anyway" if saw_prompt else "answered without the secret",
            )
        )

    ok = True
    for name, passed, detail in results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} :: {detail}")
        ok = ok and passed

    if not args.keep:
        shutil.rmtree(home, ignore_errors=True)
    print("\nverdict:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
