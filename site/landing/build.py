"""Build the 智策 marketing site into ``dist/``.

Static site, standard library only — same rule as ``site/download``: no build
toolchain, nothing to install, Cloudflare Pages can serve ``dist/`` as-is.

Every volatile number (version, byte counts, SHA256, download URLs) comes from
``site/download/release.json`` and every brand colour comes from
``brand/brand.yaml``. Neither is written into the template by hand: an unknown
``{{token}}`` is a hard error, so a template can never ship with a blank where
a version number belongs.

    python site/landing/build.py                 # render dist/
    python site/landing/build.py --check         # assert dist/ is up to date
    python site/landing/build.py --from-github   # refresh release.json first
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SRC = HERE / "src"
DIST = HERE / "dist"
RELEASE_JSON = HERE.parent / "download" / "release.json"
BRAND_YAML = REPO / "brand" / "brand.yaml"
SITE_JSON = HERE / "site.json"

TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


# --------------------------------------------------------------------------
# brand
# --------------------------------------------------------------------------


def load_brand() -> dict:
    """Minimal reader for the handful of keys we need out of brand.yaml.

    The repo's own ``scripts/rebrand.py`` owns brand parsing; this only reads
    ``name`` and ``colors`` so the site build stays dependency-free.
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None  # fall through to the line scanner below

    text = BRAND_YAML.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        return {
            "name_zh": (data.get("name") or {}).get("zh", "智策"),
            "name_en": (data.get("name") or {}).get("en", "zcagent"),
            "color": ((data.get("colors") or {}).get("brand") or "#3D5A80").upper(),
            "upstream_hex": (
                (data.get("colors") or {}).get("upstream_hex") or "#e85d75"
            ).upper(),
        }

    def scalar(key: str, default: str) -> str:
        m = re.search(rf"^\s*{key}:\s*(.+)$", text, re.M)
        return m.group(1).strip().strip('"') if m else default

    return {
        "name_zh": scalar("zh", "智策"),
        "name_en": scalar("en", "zcagent"),
        "color": scalar("brand", "#3D5A80").upper(),
        "upstream_hex": scalar("upstream_hex", "#e85d75").upper(),
    }


def shade(hex_color: str, amount: float) -> str:
    """Lighten (amount > 0) or darken (amount < 0) a hex colour."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    if amount >= 0:
        r, g, b = (round(c + (255 - c) * amount) for c in (r, g, b))
    else:
        r, g, b = (round(c * (1 + amount)) for c in (r, g, b))
    return "#%02X%02X%02X" % (r, g, b)


# --------------------------------------------------------------------------
# release
# --------------------------------------------------------------------------


def mib(nbytes: int) -> str:
    return f"{nbytes / 1024 / 1024:.1f}"


def short_hash(digest: str) -> str:
    return f"{digest[:8]}…{digest[-6:]}"


def load_release() -> dict:
    return json.loads(RELEASE_JSON.read_text(encoding="utf-8"))


def refresh_from_github(rel: dict) -> dict:
    """Re-pull the authoritative numbers for the pinned tag from the Release API.

    Fails loudly when a digest is missing: a download page without a checksum
    is worse than no download page.
    """
    api = f"https://api.github.com/repos/{rel['repo']}/releases/tags/{rel['tag']}"
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json"})
    token = rel.get("github_token") or _gh_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)

    by_name = {a["name"]: a for a in payload.get("assets", [])}
    for key, asset in rel["assets"].items():
        live = by_name.get(asset["name"])
        if live is None:
            raise SystemExit(f"release {rel['tag']} has no asset named {asset['name']}")
        digest = live.get("digest") or ""
        if "sha256:" not in digest:
            raise SystemExit(
                f"{asset['name']}: Release API returned no sha256 digest "
                f"(got {digest!r}) — refusing to write an unverified download page"
            )
        asset["bytes"] = live["size"]
        asset["sha256"] = digest.split(":", 1)[1]
        asset["id"] = live["id"]
    RELEASE_JSON.write_text(
        json.dumps(rel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"refreshed {rel['tag']} from the Release API")
    return rel


def _gh_token() -> str:
    import os
    import subprocess

    for env in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(env):
            return os.environ[env]
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=20
        )
        return out.stdout.strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------


def build_tokens(brand: dict, rel: dict) -> dict:
    exe = rel["assets"]["exe"]
    zipped = rel["assets"]["zip"]
    prev = rel.get("previous") or {}
    site = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    site_url = site["site_url"].rstrip("/")
    return {
        "NAME_ZH": brand["name_zh"],
        "NAME_EN": brand["name_en"],
        "BRAND_COLOR": brand["color"],
        "BRAND_COLOR_DARK": shade(brand["color"], -0.18),
        "BRAND_COLOR_LIGHT": shade(brand["color"], 0.88),
        "BRAND_COLOR_TINT": shade(brand["color"], 0.94),
        "SITE_URL": site_url,
        "UPSTREAM": rel.get("upstream", "TencentCloud/Octop"),
        "REPO_URL": f"https://github.com/{rel['repo']}",
        "VERSION": rel["version"],
        "VERSION_TAG": "v" + rel["version"].replace("+", "-"),
        "TAG": rel["tag"],
        "RELEASE_DATE": rel["date"],
        "RELEASE_URL": rel["release_url"],
        "TESTED_ON": rel["tested_on"],
        "RUNTIME": rel["runtime"],
        "PORTABLE_MIB": str(rel["portable_extracted_mib"]),
        "EXE_NAME": exe["name"],
        "EXE_BYTES": f"{exe['bytes']:,}",
        "EXE_MIB": mib(exe["bytes"]),
        "EXE_SHA256": exe["sha256"],
        "EXE_SHA_SHORT": short_hash(exe["sha256"]),
        "EXE_URL": exe["url"],
        "ZIP_NAME": zipped["name"],
        "ZIP_BYTES": f"{zipped['bytes']:,}",
        "ZIP_MIB": mib(zipped["bytes"]),
        "ZIP_SHA256": zipped["sha256"],
        "ZIP_SHA_SHORT": short_hash(zipped["sha256"]),
        "ZIP_URL": zipped["url"],
        "PREV_VERSION": prev.get("version", ""),
        "PREV_TAG": prev.get("tag", ""),
        "PREV_REASON": prev.get("reason", ""),
        "PREV_URL": f"https://github.com/{rel['repo']}/releases/tag/{prev.get('tag', '')}",
    }


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

TEXT_SUFFIXES = {
    ".html",
    ".css",
    ".js",
    ".txt",
    ".xml",
    ".json",
    ".webmanifest",
    ".md",
}


def render(template: str, tokens: dict, where: str) -> str:
    missing = sorted({m for m in TOKEN_RE.findall(template) if m not in tokens})
    if missing:
        raise SystemExit(
            f"{where}: template uses tokens that no data source provides: "
            f"{', '.join(missing)}"
        )
    return TOKEN_RE.sub(lambda m: tokens[m.group(1)], template)


def build_og_cover(tokens: dict) -> str | None:
    """Compose the social card. Skipped (with a note) when Pillow is absent."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  note: Pillow not installed, skipping assets/og-cover.png")
        return None

    w, h = 1200, 630
    brand = tokens["BRAND_COLOR"]
    bg = Image.new("RGB", (w, h), brand)
    draw = ImageDraw.Draw(bg)

    # Soft diagonal wash so the flat brand colour doesn't read as a colour chip.
    for i in range(h):
        t = i / h
        draw.line(
            [(0, i), (w, i)],
            fill=(
                int(brand[1:3], 16) + int((255 - int(brand[1:3], 16)) * 0.18 * t),
                int(brand[3:5], 16) + int((255 - int(brand[3:5], 16)) * 0.18 * t),
                int(brand[5:7], 16) + int((255 - int(brand[5:7], 16)) * 0.18 * t),
            ),
        )

    def font(kind: str, size: int):
        for path in (
            "C:/Windows/Fonts/msyhbd.ttc" if kind == "bold" else "C:/Windows/Fonts/msyh.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    white = (255, 255, 255)
    draw.text((80, 150), tokens["NAME_ZH"], font=font("bold", 108), fill=white)
    draw.text((80, 288), "把 AI 助手，装在你自己的机器上", font=font("bold", 46), fill=white)
    draw.text(
        (80, 366),
        "自托管 · 多用户 · 数据不出内网",
        font=font("regular", 30),
        fill=(255, 255, 255),
    )

    logo = SRC / "assets" / "logo_horizontal_white.png"
    if logo.exists():
        mark = Image.open(logo).convert("RGBA")
        scale = 150 / mark.height
        mark = mark.resize((int(mark.width * scale), 150), Image.LANCZOS)
        bg.paste(mark, (80, 60), mark)

    out = DIST / "assets" / "og-cover.png"
    bg.save(out, optimize=True)
    return "assets/og-cover.png"


def copy_static(tokens: dict) -> list[str]:
    """Everything under src/: text files go through the token renderer, the
    rest is copied byte-for-byte."""
    written = []
    for path in sorted(SRC.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(SRC)
        target = DIST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in TEXT_SUFFIXES:
            target.write_text(
                render(path.read_text(encoding="utf-8"), tokens, str(path)),
                encoding="utf-8",
            )
        else:
            shutil.copy2(path, target)
        written.append(str(rel).replace("\\", "/"))
    return written


def pull_brand_assets() -> list[str]:
    """Logo / icon / PWA files come straight from the brand pipeline's output.

    Copying them by hand is how the desktop splash ended up showing upstream's
    octopus: a hand copy drifts. Take the bytes the pipeline already produced.
    """
    public = REPO / "dashboard" / "public"
    wanted = [
        "logo_horizontal_dark.png",
        "logo_horizontal_white.png",
        "logo_vertical_dark.svg",
        "logo_vertical_white.svg",
        "favico.svg",
        "apple-touch-icon.png",
        "pwa-192.png",
        "pwa-512.png",
    ]
    copied = []
    for name in wanted:
        src = public / name
        if not src.exists():
            raise SystemExit(f"brand asset missing from the pipeline output: {src}")
        target = DIST / "assets" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(f"assets/{name}")
    return copied


def build() -> int:
    """Render into DIST (module global -- --check points it at a scratch dir)."""
    brand = load_brand()
    rel = load_release()
    tokens = build_tokens(brand, rel)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    if not any(SRC.rglob("*.html")):
        raise SystemExit(f"no HTML templates under {SRC}")

    written = sorted(copy_static(tokens))
    written += sorted(pull_brand_assets())
    og = build_og_cover(tokens)
    if og:
        written.append(og)

    # One page today; the sitemap is generated rather than hand-maintained so
    # adding a page cannot leave a stale entry behind.
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{tokens['SITE_URL']}/</loc></url>\n"
        "</urlset>\n",
        encoding="utf-8",
    )
    written.append("sitemap.xml")

    for name in written:
        print(f"  {name}")
    print(f"built {len(written)} file(s) -> {DIST}")
    return 0


def check() -> int:
    """Assert the committed dist/ is byte-identical to a fresh render.

    Renders into a scratch directory and diffs that against dist/. Comparing
    the render against the inputs it came from would be a tautology -- it can
    only ever pass, which is a green light wired to nothing.
    """
    published = DIST
    scratch = HERE / "dist-check"
    if not published.exists():
        print("dist/ does not exist -- run `python site/landing/build.py` first")
        return 1
    try:
        globals()["DIST"] = scratch
        build()
        globals()["DIST"] = published

        fresh = {
            str(p.relative_to(scratch)).replace("\\", "/")
            for p in scratch.rglob("*")
            if p.is_file()
        }
        live = {
            str(p.relative_to(published)).replace("\\", "/")
            for p in published.rglob("*")
            if p.is_file()
        }
        problems = [f"not published: {n}" for n in sorted(fresh - live)]
        problems += [f"left over in dist/: {n}" for n in sorted(live - fresh)]
        for name in sorted(fresh & live):
            if (scratch / name).read_bytes() != (published / name).read_bytes():
                problems.append(f"stale: {name}")

        if problems:
            print("dist/ is out of date -- run `python site/landing/build.py`:")
            for p in problems:
                print(f"  {p}")
            return 1
        print(f"dist/ matches templates and data ({len(fresh)} file(s))")
        return 0
    finally:
        globals()["DIST"] = published
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="assert dist/ is current")
    ap.add_argument(
        "--from-github", action="store_true", help="refresh release.json first"
    )
    args = ap.parse_args()

    if args.from_github:
        refresh_from_github(load_release())

    if args.check:
        return check()

    return build()


if __name__ == "__main__":
    sys.exit(main())