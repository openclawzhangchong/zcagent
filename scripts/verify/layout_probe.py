"""Measure the dashboard's real column layout at desktop width, per layout mode.

``PLAN-z10.md`` M1 flips the default layout from ``classic`` (nav + chat-history
rail + content) to ``minimal`` (nav that hosts the rail). Both modes already
exist, so the decision hinges on what each one *renders*, which reading source
cannot answer: in minimal the session list is a lower pane that the same column
also uses for settings (``Sidebar.tsx`` ``hidden={isRailCollapsed || minimalPane
!== "records"}``), so switching to the settings pane may hide "new chat" too.

Boots a scratch control plane (own ``OCTOP_HOME``, spare port, never another
server's database), walks the setup wizard over HTTP, then drives the built
dashboard in a browser at 1280x800 and records, for each layout state: how many
columns are visible, whether the history rail is inside the nav column, and
which affordances survive the pane switch.

    python scripts/verify/layout_probe.py --python .venv/Scripts/python.exe

Writes PNGs + JSON beside ``--out`` (default ``.zc-verify/layout``).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAIL_ID = "octop-chat-history-rail"
VIEWPORT = {"width": 1280, "height": 800}

# The three states a user can be in after M1 lands: today's default, the
# proposed default, and the pane a minimal-mode user can easily get stuck in.
STATES: tuple[tuple[str, str, str], ...] = (
    ("classic", "classic", "records"),
    ("minimal-records", "minimal", "records"),
    ("minimal-settings", "minimal", "settings"),
)


def log(msg: str) -> None:
    print(msg, flush=True)


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def api(base: str, method: str, path: str, body: Any = None, token: str | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {raw[:400]}") from exc


def boot(python: str, home: Path, port: int) -> subprocess.Popen:
    """Start a greenfield server; the control plane only opens once we bind it."""
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OCTOP_HOME"] = str(home)
    env["OCTOP_DATABASE_SQLITE_PATH"] = str(home / "octop.db")
    env["OCTOP_REQUIRE_SETUP_PASSWORD"] = "0"
    env["OCTOP_KNOWLEDGE_MODEL_PREFETCH"] = "off"
    logfile = (home.parent / "server.log").open("wb", buffering=0)
    proc = subprocess.Popen(
        [python, "-m", "octop", "run", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        cwd=str(ROOT),
        stdout=logfile,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"server exited early ({proc.returncode}) -- see server.log")
        try:
            if api(base, "GET", "/api/health") is not None:
                return proc
        except SystemExit:
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server never answered /api/health")


def run_setup(base: str, password: str, *, with_model: bool) -> str:
    """Walk the wizard.

    With *with_model* off this is the exact path a novice takes: the model step
    is skipped and the default expert has nothing to run on. With it on, a
    provider row is created before ``finish`` -- provider creation performs no
    live probe (``api/routers/providers.py:214-230``) and
    ``ProviderStore.iter_usable_rows`` only wants ``enabled`` + base_url + key +
    one chat-eligible model (``providers/store.py:111-125``), so the expert
    reaches ``ready`` without any real endpoint. That is what makes the session
    rail render rows at all, which the layout measurement needs.
    """
    status = api(base, "GET", "/api/setup/status")
    if not status.get("setup_required"):
        raise SystemExit("scratch instance is not greenfield -- refusing to reuse it")
    token = api(base, "POST", "/api/setup/begin")["wizard_token"]
    api(
        base,
        "POST",
        "/api/setup/database",
        {"driver": "sqlite", "sqlite_path": None},
        token=token,
    )
    api(
        base,
        "POST",
        "/api/setup/initial-admin",
        {"username": "admin", "password": password, "display_name": "探针", "locale": "zh"},
        token=token,
    )
    session = api(base, "POST", "/api/auth/login", {"username": "admin", "password": password})
    access = str(session.get("access_token") or session.get("token") or "")
    if not access:
        raise SystemExit(f"login returned no token: {list(session)}")
    if with_model:
        api(
            base,
            "POST",
            "/api/admin/providers",
            {
                "name": "probe-chat",
                "kind": "openai",
                "base_url": "http://127.0.0.1:9/v1",
                "api_key": "probe-not-a-real-key",
                "models": [{"id": "probe-model", "name": "探针模型", "enabled": True}],
            },
            token=access,
        )
    api(base, "POST", "/api/setup/finish", {}, token=token)
    return access


def wait_expert_running(base: str, token: str, timeout_s: int = 90) -> dict[str, str]:
    """The rail only lists sessions once the expert is ``running`` (``agentError.ts:64-70``).

    Measuring before that renders an empty rail in *every* mode, which would
    make the layout verdict meaningless.
    """
    deadline = time.time() + timeout_s
    states: dict[str, str] = {}
    while time.time() < deadline:
        agents = api(base, "GET", "/api/agents", token=token)
        rows = agents if isinstance(agents, list) else agents.get("agents") or agents.get("items") or []
        states = {
            str(r.get("agent_id") or r.get("id")): str(r.get("state"))
            for r in rows
        }
        if "running" in states.values():
            return states
        time.sleep(2)
    return states


def seed_threads(base: str, token: str, count: int) -> int:
    """Give the default expert a few threads so the session list is not empty.

    ``POST /agents/{id}/threads`` takes no body and resets the dashboard session
    each time, so the seeded threads arrive untitled -- enough to make the rail
    render rows, which is all this probe measures.
    """
    agents = api(base, "GET", "/api/agents", token=token)
    rows = agents if isinstance(agents, list) else agents.get("agents") or agents.get("items") or []
    if not rows:
        return 0
    agent_id = str(rows[0].get("agent_id") or rows[0].get("id"))
    made = 0
    for _ in range(count):
        try:
            api(base, "POST", f"/api/agents/{agent_id}/threads", None, token=token)
            made += 1
            time.sleep(0.2)
        except SystemExit:
            break
    return made


MEASURE_JS = """
(args) => {
  const rail = document.getElementById(args.railId);
  const vis = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    if (el.hidden) return false;
    const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden' && +st.opacity !== 0;
  };
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  // The app row is the first ancestor of the content column that ALSO contains
  // the nav's new-chat button -- i.e. the button sits in a sibling column.
  // Anchoring this way survives both layouts: in classic the rail is its own
  // child of that row, in minimal the rail lives inside the nav column.
  // Do NOT select the nav by [class*="sidebar" i]: CSS modules emit
  // "Sidebar-module__*" for every sidebar class, so a case-insensitive match
  // lands on whichever one comes first in the DOM, not on the column.
  const content = document.querySelector('[class*="page-container"]');
  const btn = document.querySelector('[data-testid="nav-new-chat"]');
  let row = null;
  for (let el = content; el && el.parentElement; el = el.parentElement) {
    const p = el.parentElement;
    if (p.children.length >= 2 && p.contains(btn) && !el.contains(btn)) {
      row = p;
      break;
    }
  }
  const columns = row ? [...row.children].filter(vis).map(box) : [];
  const nav = row ? [...row.children].find((c) => c.contains(btn)) : null;
  const railInsideNav = !!(rail && nav && nav.contains(rail));
  const NEW = /新对话|新建对话|new chat|newchat/i;
  const labeled = [...document.querySelectorAll('button, a')].filter(
    (el) => vis(el) && (NEW.test(el.getAttribute('aria-label') || '') || NEW.test((el.textContent || '').replace(/\\s+/g, '')))
  );
  return {
    railPresent: !!rail,
    railVisible: vis(rail),
    railBox: box(rail),
    railParentIsNav: railInsideNav,
    railInContentColumn: rail ? !railInsideNav : null,
    columnCount: columns.length,
    columnBoxes: columns,
    newChatCount: labeled.length,
    newChatInNav: nav ? labeled.filter((el) => nav.contains(el)).length : 0,
    navItemCount: nav ? nav.querySelectorAll('[class*="navItemMain"]').length : 0,
    bodyText: (document.body.innerText || '').slice(0, 400),
  };
}
"""


def probe(base: str, token: str, out: Path, shots: Path) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    results: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        for engine in ("chromium", "edge"):
            try:
                browser = (
                    pw.chromium.launch()
                    if engine == "chromium"
                    else pw.chromium.launch(channel="msedge")
                )
                break
            except Exception as exc:  # noqa: BLE001
                log(f"  {engine} unavailable: {str(exc)[:120]}")
        else:
            raise SystemExit("no browser available -- install one or run with --skip-browser")
        context = browser.new_context(viewport=VIEWPORT, locale="zh-CN")
        page = context.new_page()
        page.add_init_script(
            f"""
            localStorage.setItem('auth_token', {json.dumps(token)});
            localStorage.setItem('octop:locale', 'zh');
            """
        )
        for name, mode, pane in STATES:
            page.add_init_script(
                f"""
                localStorage.setItem('octop:layout-mode', {json.dumps(mode)});
                localStorage.setItem('octop:sidebar-minimal-pane-v2', {json.dumps(pane)});
                """
            )
            page.goto(f"{base}/chat", wait_until="domcontentloaded", timeout=60_000)
            with contextlib.suppress(Exception):  # measure whatever did render
                page.wait_for_selector(f"#{RAIL_ID}, [class*='page-container']", timeout=20_000)
            page.wait_for_timeout(2500)
            data = page.evaluate(MEASURE_JS, {"railId": RAIL_ID})
            data["state"] = name
            data["mode"] = mode
            data["pane"] = pane
            png = shots / f"{name}.png"
            page.screenshot(path=str(png), full_page=False)
            data["screenshot"] = png.relative_to(out.parent).as_posix()
            results.append(data)
            log(
                f"  {name:18s} columns={data['columnCount']} "
                f"railVisible={data['railVisible']} railInNav={data['railParentIsNav']} "
                f"newChat total/nav={data['newChatCount']}/{data['newChatInNav']} "
                f"navItems={data['navItemCount']}"
            )
        browser.close()
    return results


INTERACT_JS = """
() => {
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  const vis = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    if (el.hidden) return false;
    const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden' && +st.opacity !== 0;
  };
  const rail = document.getElementById('octop-chat-history-rail');
  const newChat = document.querySelector('[data-testid="nav-new-chat"]');
  return {
    path: location.pathname,
    railVisible: vis(rail),
    railBox: box(rail),
    newChatBox: box(newChat),
    sessionRows: document.querySelectorAll('[class*="sessionItem" i] a, [class*="sessionRow" i]').length,
  };
}
"""


def interact(base: str, token: str, shots: Path) -> dict[str, Any]:
    """Click the two controls this probe exists to guard, and record what changed.

    Reading source cannot answer "does expanding the history rail collapse the
    nav", because both are effects of one event handler in ``MainLayout``.
    Nav width is measured through the new-chat button inside it: expanded nav
    gives it ~192px, collapsed nav caps it at 40px.
    """
    from playwright.sync_api import sync_playwright

    out: dict[str, Any] = {"steps": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        context = browser.new_context(viewport=VIEWPORT, locale="zh-CN")
        page = context.new_page()
        page.add_init_script(
            f"""
            localStorage.setItem('auth_token', {json.dumps(token)});
            localStorage.setItem('octop:locale', 'zh');
            localStorage.setItem('octop:layout-mode', 'classic');
            localStorage.setItem('octop:chat-sidebar:open', 'false');
            """
        )
        page.goto(f"{base}/chat", wait_until="domcontentloaded", timeout=60_000)
        with contextlib.suppress(Exception):
            page.wait_for_selector('[data-testid="nav-new-chat"]', timeout=20_000)
        page.wait_for_timeout(2000)

        before = page.evaluate(INTERACT_JS)
        out["steps"].append({"name": "classic-before", **before})

        expand = page.get_by_role("button", name="展开对话历史")
        if expand.count() == 0:
            out["steps"].append({"name": "expand-button", "error": "not found"})
        else:
            expand.first.click()
            page.wait_for_timeout(1200)
            after = page.evaluate(INTERACT_JS)
            out["steps"].append({"name": "classic-after-expand", **after})
            page.screenshot(path=str(shots / "interact-rail-expanded-nav-collapsed.png"))
            nav_w = (after.get("newChatBox") or {}).get("w", 999)
            out["nav_collapsed_on_expand"] = bool(nav_w <= 60 and after["railVisible"])

        page.click('[data-testid="nav-new-chat"]')
        page.wait_for_timeout(1500)
        after_new = page.evaluate(INTERACT_JS)
        out["steps"].append({"name": "after-new-chat", **after_new})
        page.screenshot(path=str(shots / "interact-new-chat.png"))
        out["new_chat_reached"] = bool(
            after_new["path"].startswith("/chat/") and after_new["path"] != "/chat/"
        )
        browser.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python", default=sys.executable, help="interpreter that can import octop")
    ap.add_argument("--port", type=int, default=8097)
    ap.add_argument(
        "--out",
        default=str(ROOT / ".zc-verify" / "layout"),
        help="scratch OCTOP_HOME + report live here",
    )
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument(
        "--no-model",
        action="store_true",
        help="skip the model step like a novice does, so the expert stays unconfigured",
    )
    ap.add_argument(
        "--expect-fixed",
        action="store_true",
        help="assert the M1 outcome: the records pane survives the settings-pane switch",
    )
    args = ap.parse_args()

    if not port_is_free(args.port):
        raise SystemExit(f"port {args.port} is busy -- refusing to read another server")
    out = Path(args.out)
    home = out / "home"
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    # Our own scratch profile from a previous run; a reused one is already
    # past the wizard and the probe measures nothing about first-run.
    if home.exists():
        shutil.rmtree(home)

    password = "Probe!" + os.urandom(4).hex()
    log(f"[1/5] booting scratch control plane at {home} on :{args.port}")
    proc = boot(args.python, home, args.port)
    base = f"http://127.0.0.1:{args.port}"
    try:
        log(f"[2/5] running the wizard (model step {'skipped' if args.no_model else 'backed by a fake provider'})")
        token = run_setup(base, password, with_model=not args.no_model)
        log("       waiting for the default expert to reach 'running'")
        states = wait_expert_running(base, token)
        log(f"       expert states: {states or 'none'}")
        if not args.no_model and "running" not in states.values():
            raise SystemExit(
                f"expert never came up ({states}) -- the rail would be empty in every "
                "mode and the layout verdict would be meaningless"
            )
        made = seed_threads(base, token, args.threads)
        log(f"       seeded {made}/{args.threads} threads")

        index = Path(ROOT / "src/octop/dashboard/index.html")
        artifact = index.stat().st_mtime if index.exists() else None
        report = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "viewport": VIEWPORT,
            "model_step": "skipped" if args.no_model else "fake provider seeded",
            "expert_states": states,
            "dashboard_artifact_mtime": artifact,
            "states": [],
        }
        log("[3/5] measuring each layout state at 1280x800")
        report["states"] = probe(base, token, out, shots)

        log("[4/5] clicking the rail-expand and new-chat controls")
        report["interaction"] = interact(base, token, shots)
        it = report["interaction"]
        log(
            f"  rail-expand collapses nav: {it.get('nav_collapsed_on_expand')}  "
            f"new-chat opens a thread: {it.get('new_chat_reached')}"
        )

        log("[5/5] verdict")
        bad = []
        notes = []
        by = {s["state"]: s for s in report["states"]}
        if it.get("nav_collapsed_on_expand") is not True:
            bad.append(
                "expanding the chat-history rail left the nav expanded -- the rail and the "
                "nav now compete for width (PLAN-z10 item 2)"
            )
        if it.get("new_chat_reached") is not True:
            bad.append(
                "the nav 新建对话 button did not land on /chat/<agent> -- a fresh conversation "
                "is not reachable from the nav (PLAN-z10 item 3)"
            )
        if not by["classic"]["railInContentColumn"]:
            bad.append("classic: rail is not its own column -- probe selector is wrong")
        if not by["minimal-records"]["railParentIsNav"]:
            bad.append("minimal/records: rail did not move into the nav column")
        hidden = not by["minimal-settings"]["railVisible"]
        if hidden != bool(not args.expect_fixed):
            bad.append(
                "minimal/settings: records pane is "
                + ("hidden -- the settings pane swallows the session list and the new-chat "
                   "entry (PLAN-z10 M1; fix by making settings an overlay)" if hidden else
                   "visible -- expected hidden without --expect-fixed, so the probe selector "
                   "or the layout changed underneath it")
            )
        # The pane switch hiding the rail *is* the loss of history; that assertion
        # stands on its own. "new chat" is only comparable between states, because
        # the control is hover-revealed and this probe never hovers -- all-zero
        # means the detector is blind, not that the button is gone.
        if by["minimal-settings"]["newChatCount"] < by["minimal-records"]["newChatCount"]:
            bad.append(
                "minimal/settings: fewer 'new chat' controls than minimal/records -- "
                "the pane switch removes the entry point (PLAN-z10 M1)"
            )
        if not any(by[s]["newChatCount"] for s in by):
            notes.append(
                "new-chat detector saw nothing in any state (hover-revealed control); "
                "relying on railVisible for the pane finding"
            )
        if by["classic"]["navItemCount"] < 3:
            bad.append("nav item count looks unmeasured -- selector is wrong")
        report["notes"] = notes
        for line in notes:
            log(f"  ~ {line}")
        report["verdict"] = "OK" if not bad else "FINDINGS"
        report["findings"] = bad
        for line in bad:
            log(f"  ! {line}")
        log(f"  verdict: {report['verdict']}")

        dest = out / "report.json"
        dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  report: {dest}")
        return 0 if not bad else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
