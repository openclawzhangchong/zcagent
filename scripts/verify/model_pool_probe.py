"""Prove why the model pool stays empty after "获取模型列表", and that the UI now says so.

The reported symptom: a custom provider was added, its model list was fetched
(20 models), the card reads "20 个模型" and 已授权, yet 可用模型池 says
"暂无可用模型，请先授权至少一个提供商并配置模型" -- pointing at authorization,
which was already done.

The mechanism is not in the backend at all. ``CustomProviderModal.tsx:127``,
``PresetProviderModal.tsx:133`` and ``ProviderConfigModal.tsx:879`` all store
every fetched model with ``enabled: false`` on purpose (auto-route is meant to be
curated), and ``is_chat_eligible_model`` drops those rows -- so
``GET /api/providers/resolved`` legitimately returns ``[]``. Nothing in the UI
revealed the missing step: the only string that said "默认未启用" was a dead
locale key, and the toast that did fire claimed the models were simply added.

This script reproduces the state over HTTP, then drives the built dashboard at
1280x800 to check the three things the fix is responsible for: the card states
the enabled/total split, the empty pool names the provider to fix, and 全部启用
turns the whole list on in one click.

    python scripts/verify/model_pool_probe.py --python .venv/Scripts/python.exe

Writes PNGs + JSON beside ``--out`` (default ``.zc-verify/model-pool``).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "verify"))

import layout_probe as lp  # noqa: E402

VIEWPORT = {"width": 1280, "height": 800}
PROVIDER_NAME = "本地网关"

# Exactly the shape the dashboard writes after 获取模型列表.
FETCHED_MODELS = [
    {"id": "glm-5.1", "name": "glm-5.1", "enabled": False, "input": ["text"], "thinking": None},
    {
        "id": "deepseek-v4-pro",
        "name": "deepseek-v4-pro",
        "enabled": False,
        "input": ["text"],
        "thinking": None,
    },
    {"id": "auto", "name": "auto", "enabled": False, "input": ["text"], "thinking": None},
]


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def text_of(page: Any, selector: str) -> str:
    loc = page.locator(selector).first
    if loc.count() == 0:
        return ""
    with contextlib.suppress(Exception):
        return str(loc.inner_text(timeout=5000)).strip()
    return ""


MODELS_PAGE_JS = r"""
() => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const cards = [...document.querySelectorAll('.octop-card')];
  const card = cards.find((c) => clean(c.innerText).includes('本地网关'));
  const pool = [...document.querySelectorAll('h3')]
    .find((h) => clean(h.innerText).includes('可用模型池'));
  let scope = null;
  for (let el = pool; el && !scope; el = el.parentElement) {
    if (String(el.className).includes('poolSection')) scope = el;
  }
  const empty = scope && scope.querySelector('.octop-empty-description');
  const countTag = scope && scope.querySelector('[class*="poolCountTag"]');
  return {
    path: location.pathname,
    cardCount: cards.length,
    cardTitles: cards.map((c) => clean(c.innerText).slice(0, 40)),
    nameAnywhere: document.body.innerText.includes('本地网关'),
    cardFound: !!card,
    cardText: card ? clean(card.innerText) : '',
    poolFound: !!pool,
    poolScopeFound: !!scope,
    poolEmptyText: empty ? clean(empty.innerText) : '',
    poolCountText: countTag ? clean(countTag.innerText) : '',
    poolModelRows: scope
      ? scope.querySelectorAll('[class*="poolModelRow"]').length
      : 0,
  };
}
"""

EDITOR_JS = r"""
() => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const scope = document.querySelector('.octop-drawer-body')
    || document.querySelector('.octop-modal-body');
  if (!scope) return {open: false, buttons: [], disabledSwitches: 0};
  const buttons = [...scope.querySelectorAll('button')]
    .map((b) => clean(b.innerText))
    .filter(Boolean);
  const rows = [...scope.querySelectorAll('[class*="modelListItem"]')];
  const off = rows.filter((r) => {
    const sw = r.querySelector('.octop-switch');
    return sw && !sw.className.includes('octop-switch-checked');
  }).length;
  return {
    open: true,
    buttons,
    modelRows: rows.length,
    disabledSwitches: off,
  };
}
"""


def click_named(page: Any, label: str) -> bool:
    """Click a visible button whose text contains *label* (antd inserts a space
    between CJK glyphs, so match on the stripped form)."""
    for btn in page.locator("button").all():
        with contextlib.suppress(Exception):
            txt = str(btn.inner_text(timeout=2000)).replace(" ", "")
            if label in txt and btn.is_visible():
                btn.click()
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--out", type=Path, default=ROOT / ".zc-verify" / "model-pool")
    ap.add_argument("--skip-browser", action="store_true")
    args = ap.parse_args()

    if not port_is_free(args.port):
        raise SystemExit(f"port {args.port} is busy -- pass a spare --port")
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    shots = out / "shots"
    shots.mkdir()
    home = out / "home"
    base = f"http://127.0.0.1:{args.port}"
    report: dict[str, Any] = {"base": base}

    print("[1/5] boot scratch control plane", flush=True)
    proc = lp.boot(args.python, home, args.port)
    try:
        print("[2/5] walk the setup wizard", flush=True)
        password = "Pool!" + os.urandom(4).hex()
        token = lp.run_setup(base, password, with_model=False)
        report["password"] = password

        print("[3/5] seed the provider exactly as 获取模型列表 leaves it", flush=True)
        created = lp.api(
            base,
            "POST",
            "/api/admin/providers",
            {
                "name": PROVIDER_NAME,
                "kind": "openai",
                "base_url": "http://127.0.0.1:7863/v1",
                "api_key": "probe-key",
                "models": FETCHED_MODELS,
            },
            token=token,
        )
        pid = created["id"]
        report["provider_id"] = pid

        print("[4/5] the pool really is empty while every model is disabled", flush=True)
        resolved_before = lp.api(base, "GET", "/api/providers/resolved", token=token)
        report["resolved_before"] = len(resolved_before)
        print(f"      GET /api/providers/resolved -> {len(resolved_before)} models", flush=True)
        if len(resolved_before) != 0:
            raise SystemExit("expected 0 resolved models; the premise of this probe changed")

        if args.skip_browser:
            report["verdict"] = "SKIP-BROWSER"
            (out / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"report: {out / 'report.json'}", flush=True)
            return 0

        print("[5/5] drive the built dashboard", flush=True)
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
                raise SystemExit("no browser available -- rerun with --skip-browser")
            context = browser.new_context(viewport=VIEWPORT, locale="zh-CN")
            page = context.new_page()
            page.add_init_script(
                f"""
                localStorage.setItem('auth_token', {json.dumps(token)});
                localStorage.setItem('octop:locale', 'zh');
                """
            )
            page.goto(f"{base}/admin/models", wait_until="domcontentloaded", timeout=60_000)
            with contextlib.suppress(Exception):
                page.wait_for_selector(".octop-card", timeout=25_000)
            page.wait_for_timeout(3000)
            # The 自定义提供商 section sits below the fold; scroll so a lazy pane
            # has the same chance the human clicking down the page would give it.
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            before = page.evaluate(MODELS_PAGE_JS)
            page.screenshot(path=str(shots / "a-pool-empty.png"), full_page=True)
            report["before"] = before
            print(
                f"      cards={before['cardCount']} nameAnywhere={before['nameAnywhere']} "
                f"poolScope={before['poolScopeFound']}",
                flush=True,
            )
            print(f"      titles={before['cardTitles']}", flush=True)
            print(f"      card: {before['cardText'][:120]}", flush=True)
            print(f"      pool: {before['poolEmptyText'][:160]}", flush=True)

            # Open the provider editor through the pencil on its own card.
            opened = False
            for card in page.locator(".octop-card").all():
                with contextlib.suppress(Exception):
                    if PROVIDER_NAME not in str(card.inner_text(timeout=3000)):
                        continue
                    pencil = card.locator("svg.lucide-pencil")
                    if pencil.count():
                        pencil.first.click()
                        opened = True
                        break
            page.wait_for_timeout(2500)
            editor = page.evaluate(EDITOR_JS)
            report["editor"] = {**editor, "opened": opened}
            page.screenshot(path=str(shots / "b-editor.png"))
            print(
                f"      editor open={editor['open']} rows={editor.get('modelRows')} "
                f"off={editor.get('disabledSwitches')}",
                flush=True,
            )

            enabled_all = False
            if editor["open"]:
                enabled_all = click_named(page, "全部启用")
                page.wait_for_timeout(1200)
                after_bulk = page.evaluate(EDITOR_JS)
                report["after_bulk_enable"] = after_bulk
                page.screenshot(path=str(shots / "c-enabled.png"))
                print(
                    f"      全部启用 clicked={enabled_all} off now={after_bulk.get('disabledSwitches')}",
                    flush=True,
                )
                click_named(page, "保存")
                page.wait_for_timeout(2500)

            page.reload(wait_until="domcontentloaded")
            with contextlib.suppress(Exception):
                page.wait_for_selector(".octop-card", timeout=25_000)
            page.wait_for_timeout(3500)
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            after = page.evaluate(MODELS_PAGE_JS)
            page.screenshot(path=str(shots / "d-pool-filled.png"), full_page=True)
            report["after"] = after
            print(f"      card: {after['cardText'][:120]}", flush=True)
            print(
                f"      pool count={after['poolCountText']} rows={after['poolModelRows']}",
                flush=True,
            )
            browser.close()

        resolved_after = lp.api(base, "GET", "/api/providers/resolved", token=token)
        report["resolved_after"] = len(resolved_after)
        print(f"      GET /api/providers/resolved -> {len(resolved_after)} models", flush=True)

        checks = {
            "card states enabled/total while disabled": "已启用 0 / 3" in before["cardText"],
            "empty pool names the provider": PROVIDER_NAME in before["poolEmptyText"],
            "empty pool no longer blames authorization": "请先授权" not in before["poolEmptyText"],
            "bulk enable button present": any(
                "全部启用" in b.replace(" ", "") for b in editor.get("buttons", [])
            ),
            "bulk enable cleared every switch": (
                report.get("after_bulk_enable", {}).get("disabledSwitches") == 0
            ),
            "pool filled after save": after["poolModelRows"] > 0,
            "backend agrees": len(resolved_after) == 3,
        }
        report["checks"] = checks
        ok = all(checks.values())
        report["verdict"] = "OK" if ok else "FAIL"
        print("", flush=True)
        for name, passed in checks.items():
            print(f"  {'PASS' if passed else 'FAIL'}  {name}", flush=True)
        print(f"\nverdict: {report['verdict']}  shots: {shots}", flush=True)
        return 0 if ok else 1
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=20)
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
