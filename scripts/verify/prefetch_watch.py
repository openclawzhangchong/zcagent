"""Prove the idle embedding-model prefetch actually fires -- or actually stops.

``client_release.py`` finishes its checks seconds after the server answers, but
prefetch waits 90 s on purpose, so it needs its own run with its own clock. The
hard part is honesty: on a machine that already has the model cached, the correct
behaviour is to do nothing, and "nothing happened" looks identical to "the feature
is broken". So this script never inspects the shared ``~/.octop`` data dir. It
boots the *installed runtime* against a scratch ``OCTOP_HOME`` and a spare port,
where an empty cache means any bytes that land are this run's doing.

Two runs, one command:

    python scripts/verify/prefetch_watch.py            # enabled run + disabled run
    python scripts/verify/prefetch_watch.py --only on  # just the download
    python scripts/verify/prefetch_watch.py --runtime  # use this repo's venv instead

Exit 0 means: with the switch on the model reached disk after the idle delay and
the state machine recorded ``done``; with the switch off nothing was downloaded
and no state was written. Asserting the delay is at least ~90 s is what tells
prefetch apart from an eager download at boot.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

RUNTIME_ROOT = Path.home() / ".octop" / "portable"
MODEL = "BAAI/bge-small-zh-v1.5"
WEIGHTS_FLOOR = 90 * 1024 * 1024
IDLE_DELAY_S = 90.0
# The delay gate plus a 92 MB download on a slow link.
DOWNLOAD_BUDGET_S = 1500.0
# A disabled run only has to outlive the delay: it must decide and stay quiet.
QUIET_BUDGET_S = 200.0
POLL_S = 5.0
STATE_KEY = "knowledge_onnx_prefetch"
ATTEMPTS_KEY = "knowledge_onnx_prefetch_attempts"
PREFETCH_SWITCH = "OCTOP_KNOWLEDGE_MODEL_PREFETCH"
DONE = "done"


def log(msg: str) -> None:
    print(msg, flush=True)


def _port_free(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def weights_bytes(home: Path) -> int:
    """ONNX bytes under the scratch cache, whatever the HF alias directory is.

    ``BAAI/bge-small-zh-v1.5`` lands as ``models--Qdrant--bge-small-zh-v1.5``
    because fastembed rewrites the repo, so matching the id against a directory
    name gives a false negative. Weight files are the only stable signal.
    """
    root = home / "embedding_models"
    if not root.is_dir():
        return 0
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and f.suffix == ".onnx")


def settings_rows(home: Path) -> dict[str, str]:
    """Read the prefetch state out of the scratch DB without joining the lock."""
    db = home / "octop.db"
    if not db.is_file():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN (?, ?)", (STATE_KEY, ATTEMPTS_KEY)
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return {str(k): str(v) for k, v in rows}


def settle(home: Path, rows: dict[str, str]) -> dict[str, str]:
    """Wait for the state row after the weights have landed.

    ``prefetch_default_model`` follows the download manager, which itself polls on
    a two-second timer, so the full model is on disk a beat before ``done`` is
    written. Breaking at the first complete byte count would kill the server
    before that write and report a working feature as broken -- which is exactly
    what happened on the first z08 run.
    """
    deadline = time.time() + 30
    while rows.get(STATE_KEY) != DONE and time.time() < deadline:
        time.sleep(3)
        rows = settings_rows(home)
    return rows


def run_once(
    *,
    argv_head: list[str],
    home: Path,
    port: int,
    enabled: bool,
    budget_s: float,
) -> dict:
    """Boot the installed runtime in a scratch home and watch what prefetch does."""
    if home.exists():
        shutil.rmtree(home, ignore_errors=True)
    home.mkdir(parents=True)
    if not _port_free(port):
        raise SystemExit(f"port {port} already answers -- refusing to read another server's cache")

    env = os.environ.copy()
    env["OCTOP_HOME"] = str(home)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = ""
    # A greenfield home with no database defers the control plane until the
    # first-run wizard picks a backend, and the runtime -- prefetch included --
    # is only booted by that binding. Point the control plane at a scratch file
    # so the boot completes on its own; without this, "nothing was downloaded"
    # would mean "the server never got that far", not "the switch works".
    env["OCTOP_DATABASE_SQLITE_PATH"] = str(home / "octop.db")
    env["OCTOP_REQUIRE_SETUP_PASSWORD"] = "0"
    if enabled:
        env.pop(PREFETCH_SWITCH, None)
    else:
        env[PREFETCH_SWITCH] = "0"

    logfile = (home.parent / f"server-{'on' if enabled else 'off'}.log").open("wb", buffering=0)
    cmd = [*argv_head, "run", "--host", "127.0.0.1", "--port", str(port)]
    log(f"  booting {'with' if enabled else 'without'} prefetch on port {port}")
    boot = time.time()
    proc = subprocess.Popen(cmd, env=env, stdout=logfile, stderr=subprocess.STDOUT)

    outcome: dict = {
        "enabled": enabled,
        "home": str(home),
        "port": port,
        "budget_s": int(budget_s),
        "downloaded": False,
        "bytes": 0,
        "booted": False,
        "first_bytes_after_boot_s": None,
        "grew_monotonically": True,
        "settings": {},
    }
    sizes: list[int] = []
    first_bytes_at: float | None = None
    try:
        while time.time() - boot < budget_s:
            size = weights_bytes(home)
            if size:
                sizes.append(size)
                if first_bytes_at is None:
                    first_bytes_at = time.time()
            rows = settings_rows(home)
            done = rows.get(STATE_KEY) == DONE
            if done or size >= WEIGHTS_FLOOR:
                if not done:
                    rows = settle(home, rows)
                outcome.update(
                    {
                        "downloaded": True,
                        # Re-measure: the last polled size can predate the final file.
                        "bytes": weights_bytes(home),
                        "settings": rows,
                        "seconds_to_finish": int(time.time() - boot),
                    }
                )
                break
            if not enabled and time.time() - boot > IDLE_DELAY_S + 45:
                outcome["settings"] = rows
                outcome["observed_s"] = int(time.time() - boot)
                break
            if int(time.time() - boot) % 30 < POLL_S:
                log(f"    t={int(time.time() - boot):4d}s onnx on disk = {size / 2**20:.1f} MB")
            time.sleep(POLL_S)
    finally:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
        )
        logfile.close()

    outcome["booted"] = (home / "octop.db").is_file()
    if first_bytes_at is not None:
        outcome["first_bytes_after_boot_s"] = round(first_bytes_at - boot, 1)
    if len(sizes) > 1:
        outcome["grew_monotonically"] = all(b >= a for a, b in zip(sizes, sizes[1:], strict=False))
    log(
        f"  result: downloaded={outcome['downloaded']} bytes={outcome['bytes']:,} "
        f"settings={outcome['settings']}"
    )
    return outcome


def verify(on: dict | None, off: dict | None) -> list[str]:
    problems: list[str] = []
    for label, run in (("ON", on), ("OFF", off)):
        if run is None or run["booted"]:
            continue
        problems.append(
            f"switch {label} never created its control-plane DB, so that run proves nothing "
            f"-- read {run['home']}/../server-{'on' if label == 'ON' else 'off'}.log"
        )

    if on is not None and on["booted"]:
        if not on["downloaded"]:
            problems.append(
                "switch ON never produced the model -- check the server log for 'ONNX prefetch'"
            )
        if on["bytes"] < WEIGHTS_FLOOR:
            problems.append(f"only {on['bytes']:,} ONNX bytes, expected a full {MODEL}")
        if on["settings"].get(STATE_KEY) != DONE:
            problems.append(
                f"state row {STATE_KEY} is {on['settings'].get(STATE_KEY)!r}, not 'done'"
            )
        if int(on["settings"].get(ATTEMPTS_KEY, "0")) < 1:
            problems.append(f"{ATTEMPTS_KEY} never bumped: {on['settings']}")
        if not on["grew_monotonically"]:
            problems.append("cache shrank mid-flight -- a partial dir was replaced")
        delay = on["first_bytes_after_boot_s"]
        if delay is None:
            problems.append("no first-byte timestamp to compare against the idle delay")
        elif delay < IDLE_DELAY_S - 10:
            problems.append(f"model started at {delay}s, before the {IDLE_DELAY_S}s idle delay")

    if off is not None and off["booted"]:
        if off["downloaded"] or off["bytes"]:
            problems.append("switch OFF still downloaded the model")
        if off["settings"]:
            problems.append(f"switch OFF still wrote state: {off['settings']}")
        if off.get("observed_s", 0) <= IDLE_DELAY_S:
            problems.append(
                f"switch OFF only watched {off.get('observed_s')}s, less than the "
                f"{IDLE_DELAY_S}s idle delay it is supposed to outlive"
            )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["on", "off", "both"], default="both")
    ap.add_argument(
        "--home",
        default="",
        help="scratch dir that holds home-on / home-off (default: .zc-verify/prefetch)",
    )
    ap.add_argument(
        "--runtime",
        action="store_true",
        help="use this repo's .venv instead of the installed portable runtime",
    )
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--budget", type=float, default=DOWNLOAD_BUDGET_S)
    args = ap.parse_args()

    if args.home:
        root = Path(args.home).expanduser()
    else:
        root = Path(os.environ.get("ZC_VERIFY_DIR", str(Path.cwd() / ".zc-verify"))) / "prefetch"
    root.mkdir(parents=True, exist_ok=True)

    if args.runtime:
        python = Path.cwd() / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            raise SystemExit(f"no venv at {python}")
        argv_head = [str(python), "-m", "octop"]
    else:
        python = RUNTIME_ROOT / "runtime" / "python.exe"
        launch = RUNTIME_ROOT / "launch.py"
        if not (python.is_file() and launch.is_file()):
            raise SystemExit(
                f"installed runtime missing at {RUNTIME_ROOT}; run client_release.py first"
            )
        argv_head = [str(python), str(launch)]

    if args.runtime:
        runtime = f"repo venv ({Path.cwd() / '.venv'})"
    else:
        marker = RUNTIME_ROOT / "VERSION.txt"
        runtime = "installed runtime (version unknown)"
        if marker.is_file():
            found = dict(
                line.split("=", 1)
                for line in marker.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
            runtime = (
                f"installed {found.get('octop_version', '?')} python={found.get('python', '?')}"
            )

    log(f"proving idle prefetch for {MODEL} on {runtime}")
    on = None
    if args.only in ("on", "both"):
        on = run_once(
            argv_head=argv_head,
            home=root / "home-on",
            port=args.port,
            enabled=True,
            budget_s=args.budget,
        )
    off = None
    if args.only in ("off", "both"):
        if on is not None and not _port_free(args.port):
            log(f"  port {args.port} still busy from the previous run; waiting 15s")
            time.sleep(15)
        off = run_once(
            argv_head=argv_head,
            home=root / "home-off",
            port=args.port,
            enabled=False,
            budget_s=QUIET_BUDGET_S,
        )

    report = {"runtime": runtime, "model": MODEL, "on": on, "off": off}
    out = root / "prefetch-report.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    problems = verify(on, off)
    for line in problems:
        log(f"FAIL {line}")
    if problems:
        log(f"see {out} and the server logs beside it")
        return 1
    if on is not None:
        log(
            f"OK idle prefetch downloaded {on['bytes']:,} bytes {on['first_bytes_after_boot_s']}s "
            f"after boot and recorded {STATE_KEY}={DONE}"
        )
    if off is not None:
        log(f"OK {PREFETCH_SWITCH}=0 downloaded nothing and wrote no state")
    if on is None or off is None:
        log(f"OK --only {args.only} ran; the other half was not asserted")
    log(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
