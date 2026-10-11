"""Render the static screen mockups into the PNGs the site embeds.

The screens are hand-maintained HTML recreations of the dashboard (see
``screens/screen.css`` for where the tokens come from). Rendering them here —
rather than screenshotting a running instance — keeps the site's imagery free
of real accounts, real conversation content and internal notes, and means a
copy tweak is an HTML edit plus one command, with no server and no login.

    python site/landing/shot_screens.py

Playwright drives the browser Edge already installed on the machine, so this
adds no browser download. It is a developer tool: ``build.py`` does not need
it, and the rendered PNGs are committed.
"""

from __future__ import annotations

import http.server
import shutil
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCREENS = HERE / "screens"
OUT = HERE / "src" / "assets" / "screens"

VIEWPORT = {"width": 1600, "height": 1000}
SCALE = 2

# Which sidebar entry reads as "current" on each screen.
PAGES = [
    "chat",
    "experts",
    "knowledge",
    "channels",
    "install-wizard",
    "models",
    "kb-models",
    "forgot-password",
]


def stage_icon() -> None:
    """The sidebar mark is the pipeline's own PWA icon, not a hand copy."""
    src = REPO / "dashboard" / "public" / "pwa-512.png"
    if not src.exists():
        raise SystemExit(f"brand icon missing from the pipeline output: {src}")
    shutil.copy2(src, SCREENS / "icon.png")


def serve(directory: Path):
    handler = partial(_QuietHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence the request log
        pass


def main() -> int:
    stage_icon()
    OUT.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(SCREENS)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx = browser.new_context(
                viewport=VIEWPORT, device_scale_factor=SCALE, locale="zh-CN"
            )
            page = ctx.new_page()
            for name in PAGES:
                src = SCREENS / f"{name}.html"
                if not src.exists():
                    print(f"skip {name}: no {src.name}")
                    continue
                page.goto(f"http://127.0.0.1:{port}/{name}.html", wait_until="networkidle")
                page.wait_for_timeout(400)
                target = OUT / f"{name}.png"
                page.screenshot(path=str(target))
                print(f"  {name}.png  {target.stat().st_size // 1024} KB")
            browser.close()
    finally:
        httpd.shutdown()

    print(f"rendered {len(PAGES)} screen(s) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())