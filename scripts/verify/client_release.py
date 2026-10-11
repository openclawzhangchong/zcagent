"""End-to-end acceptance for a shipped zcagent Windows client.

This replaces the per-release throwaway scripts. One command answers "is the
artefact on the Release page actually correct when installed here?", which is the
only question that has caught real defects in this product (an upstream icon, an
English default language, a runtime that never got replaced, a brand string that
only appeared in the packaged bytes).

Usage
-----
    python scripts/verify/client_release.py --version 1.0.2b6+z07
    python scripts/verify/client_release.py --version 1.0.2b6+z07 --stage fetch
    python scripts/verify/client_release.py --version 1.0.2b6+z07 \\
        --install-dir "C:\\Program Files\\zcagent"

Stages: ``all`` (default) runs resolve -> fetch -> install -> launch -> checks.
``fetch`` stops after the download is byte- and hash-verified. ``install``
launches an already-installed build and runs the checks.

Exit code 0 means every assertion held; each failure names the assertion rather
than just the stage, because a green stage with the wrong contents is how z03's
locale fix shipped unseen.

Requires: the project venv (playwright + Pillow are already there) and a
Windows box with Edge for the browser checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = os.environ.get("ZC_VERIFY_REPO", "openclawzhangchong/zcagent")
BASE = "http://127.0.0.1:8088"
PORTABLE = Path.home() / ".octop" / "portable"
DOWNLOADS = Path(os.environ.get("ZC_VERIFY_DIR", str(Path.cwd() / ".zc-verify")))
OUT_DIR = DOWNLOADS / "reports"

# Strings that must appear in the served entry chunk, keyed by the release that
# introduced them so an older build can still be verified honestly.
BUNDLE_MARKERS = {
    "1.0.2b6+z03": 'function resolveInitialLocale(){return readStoredUiLocale()??"zh"}',
    "1.0.2b6+z06": "local-recovery",
    "1.0.2b6+z08": "prefetch_enabled",
}
# Releases from which the login page carries the account hint and self-service reset.
RECOVERY_UI_FROM = "1.0.2b6+z06"
# Releases from which the knowledge dialog curates models and notes.
CURATED_MODELS_FROM = "1.0.2b6+z08"


def log(msg: str) -> None:
    print(msg, flush=True)


def tag_of(version: str) -> str:
    return "v" + version.replace("+", "-")


def token() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def api(path: str) -> dict:
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    if tok := token():
        req.add_header("Authorization", f"Bearer {tok}")
    return json.load(urllib.request.urlopen(req, timeout=60))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def http_status(url: str) -> str:
    return subprocess.run(
        ["curl", "-s", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


# --------------------------------------------------------------------------- resolve


def stage_resolve(version: str) -> dict:
    tag = tag_of(version)
    release = api(f"/repos/{REPO}/releases/tags/{tag}")
    exe_name = f"zcagent-desktop-windows-amd64-{version}.exe"
    matches = [a for a in release["assets"] if a["name"] == exe_name]
    if not matches:
        raise SystemExit(
            f"{exe_name} is not on {tag}; assets={[a['name'] for a in release['assets']]}"
        )
    asset = matches[0]
    if not asset.get("digest"):
        raise SystemExit(
            "the Release API returned no digest -- refusing to verify against a hash we do not have"
        )
    info = {
        "version": version,
        "tag": tag,
        "id": int(asset["id"]),
        "name": asset["name"],
        "bytes": int(asset["size"]),
        "sha256": asset["digest"].removeprefix("sha256:"),
        "browser_url": asset["browser_download_url"],
    }
    log(f"resolved {info['name']}: {info['bytes']} bytes, sha256 {info['sha256'][:16]}...")
    return info


# ------------------------------------------------------------------------------ fetch


def stage_fetch(info: dict) -> Path:
    """Download with resume, then confirm size and hash.

    ``gh release download`` has returned success on a 37%-complete file here, and
    github.com transport is intermittent while api.github.com is reliable but slow,
    so the two are alternated and the byte count is the only thing trusted.
    """
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS / info["name"]
    api_url = f"https://api.github.com/repos/{REPO}/releases/assets/{info['id']}"
    headers = ["-H", "Accept: application/octet-stream"]
    if tok := token():
        headers += ["-H", f"Authorization: token {tok}"]
    for attempt in range(1, 61):
        have = dest.stat().st_size if dest.exists() else 0
        if have == info["bytes"]:
            break
        if attempt % 2:
            url, extra = info["browser_url"], []
        else:
            url, extra = api_url, headers
        subprocess.run(
            [
                "curl",
                "-sSL",
                "--connect-timeout",
                "25",
                "--max-time",
                "900",
                *extra,
                "-C",
                "-",
                "-o",
                str(dest),
                url,
            ],
            check=False,
        )
        got = dest.stat().st_size if dest.exists() else 0
        log(
            f"  attempt {attempt}: {got}/{info['bytes']} bytes "
            f"({'github' if attempt % 2 else 'api'})"
        )
    else:
        raise SystemExit("download never completed")
    actual = dest.stat().st_size
    if actual != info["bytes"]:
        raise SystemExit(f"byte count mismatch: {actual} != {info['bytes']}")
    digest = sha256_of(dest)
    if digest != info["sha256"]:
        raise SystemExit(f"SHA256 mismatch: {digest} != {info['sha256']}")
    log(f"download verified: {actual} bytes, hash matches the release digest")
    return dest


# ----------------------------------------------------------------------------- install


def portable_version() -> str:
    target = PORTABLE / "VERSION.txt"
    if not target.exists():
        return ""
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("octop_version="):
            return line.split("=", 1)[1].strip()
    return ""


def _stop_installed_client() -> list[int]:
    """Kill the running client by PID so the installer can replace its files.

    A live ``zcagent.exe`` holds an open handle on itself: NSIS under ``/S`` does
    not pop a "files in use" dialog, it just leaves the old build in place, and
    the next stage would then read the previous release's bundle and call it a
    pass.
    """
    listed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process zcagent -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    pids = [int(x) for x in listed if x.strip().isdigit()]
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
        )
    if pids:
        time.sleep(6)
    return pids


def stage_install(exe: Path, install_dir: Path, version: str) -> None:
    """Run the NSIS installer silently.

    ``/D=`` must use backslashes and be the last argument -- a forward-slash path is
    silently ignored and the installer falls back to its default directory.

    Freshness comes from the registry key the installer writes, **not** from the
    exe's mtime: NSIS stamps the payload's build time onto the file it drops, so a
    successful install looks older than the run that performed it. Judging by mtime
    failed a z08 install that had in fact replaced everything.
    """
    target = install_dir / "zcagent.exe"
    stopped = _stop_installed_client()
    if stopped:
        log(f"stopped the running client first: pid {', '.join(str(p) for p in stopped)}")
    log(f"installing silently into {install_dir} ...")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-Process -FilePath '{exe}' -ArgumentList '/S','/D={install_dir}' -Wait",
        ],
        check=False,
    )
    deadline = time.time() + 300
    while time.time() < deadline:
        got = registry_version()
        if got == version and target.exists() and target.stat().st_size > 100_000_000:
            log(f"installed: {target} ({target.stat().st_size} bytes), registry {got}")
            return
        time.sleep(3)
    raise SystemExit(
        f"installer left DisplayVersion={registry_version()!r} "
        f"with a {target.stat().st_size if target.exists() else 0}-byte exe, "
        f"expected {version!r}"
    )


def registry_version() -> str:
    out = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-ItemProperty 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion"
            "\\Uninstall\\zcagentzcagent' -ErrorAction SilentlyContinue).DisplayVersion",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return out


# ------------------------------------------------------------------------------ launch


def stage_launch(install_dir: Path) -> None:
    if http_status(f"{BASE}/login") == "200":
        raise SystemExit(
            "8088 already answers -- an older client or the dev server is running, "
            "and every check below would read its bundle instead of the new one"
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = OUT_DIR / "client-app.log"
    subprocess.Popen(
        [str(install_dir / "zcagent.exe")],
        stdout=open(log_file, "w", encoding="utf-8"),  # noqa: SIM115
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 600
    while time.time() < deadline:
        if http_status(f"{BASE}/login") == "200":
            log("server answering on 8088")
            return
        time.sleep(5)
    raise SystemExit(f"server never came up on 8088; see {log_file}")


# ------------------------------------------------------------------------------- checks


def stage_runtime(version: str, before: str) -> str:
    after = portable_version()
    log(f"unpacked runtime: {before or '(none)'} -> {after or '(none)'}")
    if after != version:
        raise SystemExit(
            f"the client is still running {after or 'nothing'}; "
            "a new build that does not replace the old runtime is the z02-z04 defect"
        )
    return after


def expected_markers(version: str) -> dict:
    return {rel: needle for rel, needle in BUNDLE_MARKERS.items() if rel <= version}


def stage_bundle(version: str) -> dict:
    html = urllib.request.urlopen(f"{BASE}/login", timeout=30).read().decode("utf-8", "replace")
    match = re.search(r'src="(/assets/index\.[A-Za-z0-9_-]+\.js)"', html)
    if not match:
        raise SystemExit("no entry chunk in the served HTML")
    chunk = match.group(1)
    js = urllib.request.urlopen(f"{BASE}{chunk}", timeout=60).read().decode("utf-8", "replace")
    found = {}
    for release, needle in expected_markers(version).items():
        present = needle in js
        found[release] = present
        log(f"  bundle carries the {release} change: {present}")
        if not present:
            raise SystemExit(f"served chunk {chunk} is missing the {release} change")
    return {"chunk": chunk, "markers": found}


def _auth_token() -> str:
    body = json.dumps(
        {"username": "admin", "password": os.environ.get("ZC_VERIFY_PASSWORD", "")}
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/api/auth/login", data=body, headers={"Content-Type": "application/json"}
    )
    return str(json.load(urllib.request.urlopen(req, timeout=20))["access_token"])


def stage_embedding_api(version: str) -> dict:
    """Ask the running server what the knowledge dialog would actually show.

    The 41-model dump and the missing per-model notes were both invisible in the
    bundle, because they are data the endpoint returns, not code it ships.
    """
    if version < CURATED_MODELS_FROM:
        return {"skipped": f"curated models exist from {CURATED_MODELS_FROM}"}
    token = _auth_token()

    def get(path: str) -> dict:
        req = urllib.request.Request(f"{BASE}/api{path}")
        req.add_header("Authorization", f"Bearer {token}")
        return json.load(urllib.request.urlopen(req, timeout=30))

    default = get("/knowledge-bases/embedding-options")["onnx"]
    expanded = get("/knowledge-bases/embedding-options?all_onnx=true")["onnx"]
    default_ids = [str(m["id"]) for m in default]
    expanded_ids = [str(m["id"]) for m in expanded]
    log(f"  default list: {len(default)} models -> {default_ids}")
    log(f"  expanded list: {len(expanded)} models")

    if len(default) > 4:
        raise SystemExit(f"recommended list leaked {len(default)} models")
    if any("clip" in mid.lower() for mid in expanded_ids):
        raise SystemExit("CLIP model is still offered for knowledge bases")
    if len(expanded) > 20:
        raise SystemExit(f"advanced list still dumps the whole fastembed catalog ({len(expanded)})")
    missing_notes = [str(m["id"]) for m in expanded if not (m.get("note_zh") and m.get("note_en"))]
    if missing_notes:
        raise SystemExit(f"models without a trade-off note: {missing_notes}")
    e5 = "intfloat/multilingual-e5-large"
    if e5 in default_ids:
        raise SystemExit("e5-large is still recommended despite needing input prefixes")
    return {"default": default_ids, "expanded_count": len(expanded), "all_notated": True}


def stage_ui(version: str) -> dict:
    """Render the login page the way WebView2 does: English navigator, no storage."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        ctx = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'language',{get:()=>'en-US'});")
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(2500)
        login_text = " ".join(page.locator("body").inner_text().split())
        stored = page.evaluate("() => localStorage.getItem('octop:ui-locale')")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT_DIR / "login.png"))

        hint_text = ""
        modal_text = ""
        has_form = False
        trigger = page.locator("text=/忘记密码|Forgot password/").first
        if trigger.count():
            trigger.click()
            page.wait_for_timeout(1500)
            modal = page.locator(".octop-modal, [role='dialog']").first
            modal_text = " ".join(modal.inner_text().split())
            has_form = modal.locator('[data-testid="login-local-reset"]').count() > 0
            hint = page.locator('[data-testid="login-existing-install-hint"]')
            hint_text = hint.inner_text() if hint.count() else ""
            page.screenshot(path=str(OUT_DIR / "forgot.png"))
        browser.close()

    def cjk(text: str) -> bool:
        return any("一" <= ch <= "鿿" for ch in text)

    result = {
        "stored_locale": stored,
        "login_is_chinese": cjk(login_text),
        "login_has_english_signin": "Sign in" in login_text,
        "account_hint": hint_text,
        "recovery_form": has_form,
        "modal_shows_cli_command": "octop user passwd" in modal_text,
    }
    for key, value in result.items():
        log(f"  {key}: {value}")
    if not result["login_is_chinese"] or result["login_has_english_signin"]:
        raise SystemExit("the login page is still English")
    if version >= RECOVERY_UI_FROM:
        if not result["recovery_form"]:
            raise SystemExit("expected the self-service reset form in the dialog")
        if result["modal_shows_cli_command"]:
            raise SystemExit(
                "the dialog still shows shell commands on a machine that can self-serve"
            )
    return result


def stage_signed_ui(version: str) -> dict:
    """Log in for real and check the two surfaces that only exist behind auth.

    The default knowledge-base name/description is a form default, and the
    first-run checklist is a *negative* feature -- it must disappear for a user
    who already has models, an expert and a conversation. Neither is visible in
    the bundle text or in a unit test; both are exactly what a release can break
    silently, so they are checked in the browser.
    """
    if version < CURATED_MODELS_FROM:
        return {"skipped": f"signed-in checks exist from {CURATED_MODELS_FROM}"}
    if not os.environ.get("ZC_VERIFY_PASSWORD"):
        raise SystemExit("ZC_VERIFY_PASSWORD is required for the signed-in checks")

    from playwright.sync_api import sync_playwright

    user_field = re.compile("用户名|Username", re.I)
    pw_re = re.compile("密码|Password", re.I)
    submit = re.compile("登录|Sign in|Log in", re.I)
    create_btn = re.compile("创建知识库|Create knowledge", re.I)
    name_label = re.compile("^名称$|^Name$", re.I)
    desc_label = re.compile("^描述$|^Description$", re.I)
    checklist_re = re.compile("发出第一条消息|Send your first message")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.add_init_script("Object.defineProperty(navigator,'language',{get:()=>'zh-CN'});")
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=90_000)
        page.get_by_placeholder(user_field).first.fill("admin")
        page.get_by_placeholder(pw_re).first.fill(os.environ["ZC_VERIFY_PASSWORD"])
        page.get_by_role("button", name=submit).first.click()
        page.wait_for_url(lambda url: "/login" not in url, timeout=45_000)

        page.goto(f"{BASE}/knowledge-bases", wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(2000)
        page.get_by_role("button", name=create_btn).first.click()
        page.wait_for_timeout(1500)
        modal = page.locator(".octop-modal, [role='dialog']").first
        name_field = modal.get_by_label(name_label)
        desc_field = modal.get_by_label(desc_label)
        if name_field.count() == 0 or desc_field.count() == 0:
            raise SystemExit(
                "the create dialog did not open: no 名称/描述 field in the modal -- "
                "check the button selector against the served build"
            )
        kb_name = name_field.first.input_value()
        kb_desc = desc_field.first.input_value()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT_DIR / "kb-create.png"))
        modal.press("Escape")

        page.goto(f"{BASE}/chat", wait_until="networkidle", timeout=90_000)
        # Positive control first: a page that never rendered would also have no
        # checklist, and "assertion passed on a blank screen" is the exact false
        # green this tool was written to refuse.
        if page.locator("textarea").count() == 0:
            raise SystemExit("/chat did not render its composer, so the checklist check is void")
        # A completed checklist is allowed to show its ticks for 1.6 s before it
        # dismisses itself, so wait past that window before calling it absent.
        page.wait_for_timeout(4000)
        checklist = page.get_by_text(checklist_re).count()
        page.screenshot(path=str(OUT_DIR / "chat-old-user.png"))
        browser.close()

    result = {
        "kb_default_name": kb_name,
        "kb_default_description": kb_desc,
        "checklist_visible_for_existing_user": checklist > 0,
    }
    for key, value in result.items():
        log(f"  {key}: {value}")
    if not kb_name.strip() or not any("一" <= ch <= "鿿" for ch in kb_name):
        raise SystemExit("the create dialog's name field is not pre-filled with a Chinese default")
    if not kb_desc.strip():
        raise SystemExit("the create dialog's description field is empty")
    if result["checklist_visible_for_existing_user"]:
        raise SystemExit(
            "the first-run checklist still renders for a machine that finished all 3 steps"
        )
    return result


def stage_icon(install_dir: Path, version: str) -> dict:
    """Read the icon out of the installed exe -- the repo never contains the .ico."""
    ps = r"""
Add-Type -AssemblyName System.Drawing
$exe = $env:ZC_ICON_EXE
$out = $env:ZC_ICON_OUT
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($exe)
if ($null -eq $icon) { exit 3 }
$bmp = $icon.ToBitmap()
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / f"icon-{version}.png"
    env = {**os.environ, "ZC_ICON_EXE": str(install_dir / "zcagent.exe"), "ZC_ICON_OUT": str(png)}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=False)
    if not png.exists():
        raise SystemExit("could not extract an icon from the installed exe")
    digest = hashlib.sha256(png.read_bytes()).hexdigest()
    log(f"  installed icon: {png} sha256 {digest[:16]}...")
    return {"icon_png": str(png), "icon_sha256": digest}


# ------------------------------------------------------------------------------- driver


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True, help="e.g. 1.0.2b6+z07")
    ap.add_argument(
        "--stage", default="all", choices=["all", "resolve", "fetch", "install", "verify"]
    )
    ap.add_argument("--install-dir", default=r"C:\Program Files\zcagent")
    args = ap.parse_args()

    install_dir = Path(args.install_dir)
    report: dict = {"version": args.version, "repo": REPO}

    info = stage_resolve(args.version)
    report["asset"] = {k: info[k] for k in ("name", "bytes", "sha256", "tag")}
    if args.stage == "resolve":
        return _finish(report)

    exe = stage_fetch(info)
    report["download"] = {"path": str(exe), "verified": True}
    if args.stage == "fetch":
        return _finish(report)

    report["runtime_before"] = portable_version()
    already_there = install_dir.exists() and (install_dir / "zcagent.exe").exists()
    if args.stage == "verify" and already_there:
        log(f"reusing the existing install at {install_dir}")
    else:
        stage_install(exe, install_dir, args.version)
    report["registry_display_version"] = registry_version()
    stage_launch(install_dir)

    report["runtime_after"] = stage_runtime(args.version, report["runtime_before"])
    report["bundle"] = stage_bundle(args.version)
    report["embedding_api"] = stage_embedding_api(args.version)
    report["ui"] = stage_ui(args.version)
    report["signed_ui"] = stage_signed_ui(args.version)
    report.update(stage_icon(install_dir, args.version))
    return _finish(report)


def _finish(report: dict) -> int:
    report["passed"] = True
    report["downloads_dir_note"] = str(DOWNLOADS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"{report['version']}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\nALL ASSERTIONS HELD -- report at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
