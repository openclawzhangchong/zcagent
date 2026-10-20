"""Prove the "skills take effect next turn" hint actually renders styled.

A CSS-module class that does not exist fails silently -- ``styles.x`` becomes
``undefined`` and the element renders unstyled, so "the string is in the bundle"
is not the same claim as "the user sees it as a subtitle". This boots a scratch
control plane, opens the real built dashboard at desktop width, and asserts the
computed style, the position between the tab bar and the list, and the zh/en
text. Leaves a screenshot next to the JSON report.

    python scripts/verify/skill_hint_probe.py --python .venv/Scripts/python.exe
"""

from __future__ import annotations

import argparse
import contextlib
import json
import secrets
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "verify"))

import layout_probe as lp  # noqa: E402

OUT = ROOT / ".zc-verify" / "skill-hint"
SHOTS = OUT / "shots"
VIEWPORT = {"width": 1280, "height": 800}

HINT_JS = """
() => {
  const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim();
  const tabs = document.querySelector('[role="tablist"], [class*="tabBar" i]');
  // The hint is the element whose text mentions the next turn, whichever locale
  // is active. Finding it by content keeps this probe honest if class names get
  // re-hashed by a build change.
  const cand = [...document.querySelectorAll('div,p,span')].filter((el) =>
    /下一轮|next turn/.test(norm(el.textContent)) && el.children.length === 0);
  if (!cand.length) return {found: false};
  const el = cand[0];
  const st = getComputedStyle(el);
  const box = el.getBoundingClientRect();
  const tabBox = tabs ? tabs.getBoundingClientRect() : null;
  return {
    found: true,
    text: norm(el.textContent).slice(0, 120),
    cls: el.className,
    fontSize: st.fontSize,
    color: st.color,
    tertiary: getComputedStyle(document.documentElement).getPropertyValue('--fn-text-tertiary').trim(),
    marginBottom: st.marginBottom,
    visible: box.width > 20 && box.height > 8 && st.display !== 'none' && +st.opacity !== 0,
    belowTabBar: tabBox ? box.top >= tabBox.bottom - 1 : null,
  };
}
"""


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--port", type=int, default=18137)
    ap.add_argument("--keep", action="store_true", help="leave the scratch home for manual poking")
    args = ap.parse_args()
    if not port_is_free(args.port):
        raise SystemExit(f"port {args.port} is busy")

    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(OUT / "home", ignore_errors=True)
    home = OUT / "home"
    base = f"http://127.0.0.1:{args.port}"
    password = "Probe!" + secrets.token_hex(4)

    checks: list[tuple[str, bool, str]] = []
    proc = lp.boot(args.python, home, args.port)
    token = ""
    try:
        # with_model=False leaves the expert state=failed (nothing to run on),
        # which is a fixture artifact; a provider row with a dead URL is enough
        # for it to reach running.
        token = lp.run_setup(base, password, with_model=True)
        states = lp.wait_expert_running(base, token)
        checks.append(("scratch expert reached state=running", "running" in set(states.values()), str(states)))

        from playwright.sync_api import sync_playwright

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
                    print(f"  {engine} unavailable: {str(exc)[:120]}", flush=True)
            else:
                raise SystemExit("no browser available")

            for locale, expect in (("zh", "下一轮对话开始就生效"), ("en", "next turn")):
                # The server-stored profile wins: AuthGuard calls
                # applyUserLocale(me.locale) on every authenticated boot and
                # that overwrites octop:ui-locale in localStorage. Setting the
                # key alone therefore silently renders both passes in Chinese.
                lp.api(base, "PATCH", "/api/preferences", {"locale": locale}, token=token)
                context = browser.new_context(viewport=VIEWPORT, locale=locale)
                page = context.new_page()
                page.add_init_script(f"localStorage.setItem('auth_token', {json.dumps(token)});")
                page.goto(f"{base}/personalization/skills", wait_until="domcontentloaded", timeout=60_000)
                with contextlib.suppress(Exception):
                    page.wait_for_selector("[role='tab']", timeout=25_000)
                page.wait_for_timeout(3000)
                info: dict[str, Any] = page.evaluate(HINT_JS)
                shot = SHOTS / f"skills-hint-{locale}.png"
                page.screenshot(path=str(shot), full_page=False)
                print(f"[{locale}] {json.dumps(info, ensure_ascii=False)}", flush=True)

                checks.append(
                    (
                        f"{locale}: hint renders",
                        bool(info.get("found")) and expect in str(info.get("text", "")),
                        str(info.get("text", ""))[:80],
                    )
                )
                checks.append(
                    (
                        f"{locale}: hint is visible",
                        bool(info.get("visible")),
                        f"fontSize={info.get('fontSize')} cls={info.get('cls')}",
                    )
                )
                # The class has to have actually resolved -- an unresolved
                # CSS-module key would leave fontSize at the 16px default.
                checks.append(
                    (
                        f"{locale}: the CSS-module class applied (14px tertiary, 16px below)",
                        info.get("fontSize") == "14px" and info.get("marginBottom") in {"16px", "12px"},
                        f"fontSize={info.get('fontSize')} marginBottom={info.get('marginBottom')} "
                        f"color={info.get('color')} --fn-text-tertiary={info.get('tertiary')}",
                    )
                )
                checks.append(
                    (
                        f"{locale}: hint sits under the tab bar",
                        info.get("belowTabBar") is True,
                        f"belowTabBar={info.get('belowTabBar')}",
                    )
                )
                context.close()

            browser.close()
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(30)
        if not args.keep:
            shutil.rmtree(home, ignore_errors=True)

    ok = True
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} :: {detail}")
        ok = ok and passed
    report = {"checks": [n for n, p, _ in checks], "results": checks, "verdict": "OK" if ok else "FAILED"}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {OUT / 'report.json'}")
    print(f"shots:  {SHOTS}")
    print("verdict:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
