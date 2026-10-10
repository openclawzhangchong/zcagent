#!/usr/bin/env python3
"""Build-time rebrand: apply brand/brand.yaml to the working tree.

OEM = edit brand/brand.yaml (+ drop a new icon), then:

    python scripts/rebrand.py --apply     # rewrite display strings and icons
    python scripts/rebrand.py --check     # fail if any old brand string survives
    python scripts/rebrand.py --revert    # git-restore everything this touched

Display layer only. Identifiers (package name, OCTOP_HOME, ~/.octop, .octop
workspace, X-Octop-* headers, prefixCls, octop:* storage keys, nav keys,
migration numbers) are deliberately left alone -- see brand/brand.yaml header.
"""

from __future__ import annotations

import argparse
import base64
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BRAND_FILE = ROOT / "brand" / "brand.yaml"

# Capitalised brand word only, with ASCII boundaries so `OctopError`,
# `OctopServer`, `X-Octop-Agent-Id`, `octop-harness` and `~/octop-login.txt`
# never match. CJK neighbours ("当前Octop版本") do match, which is intended.
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])Octop(?![A-Za-z0-9_-])")


def load_brand() -> dict:
    return yaml.safe_load(BRAND_FILE.read_text(encoding="utf-8"))


def _excluded(rel: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(rel, pat) for pat in patterns)


def transform(text: str, brand: dict, lang: str) -> str:
    for phrase in brand.get("phrases") or []:
        text = text.replace(phrase["from"], phrase["to"])
    for lit in (brand.get("identity") or {}).get("literals") or []:
        dst = lit["to"]
        pattern = lit.get("pattern")
        if pattern:
            # A literal that collides with a longer string that must survive --
            # `https://octop.cloud` is a prefix of the upstream channel endpoint
            # `https://octop.cloud.tencent.com`, so it needs a boundary.
            text = re.sub(pattern, lambda _m: dst, text)
            continue
        src = lit["from"]
        text = text.replace(src, dst)
        if "." in src:
            # Same identity written inside a regex needs its dots escaped.
            text = text.replace(src.replace(".", r"\."), dst.replace(".", r"\."))
    return TOKEN_RE.sub(brand["name"][lang], text)


def expand_braces(pattern: str) -> list[str]:
    """pathlib.glob has no {a,b} support -- expand it ourselves."""
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out: list[str] = []
    for option in m.group(1).split(","):
        out.extend(expand_braces(pattern[: m.start()] + option + pattern[m.end() :]))
    return out


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None  # binary asset (icon, archive) -- not a text target


def text_targets(brand: dict) -> list[tuple[Path, str]]:
    """Files the display-string sweep applies to, with zh/en name per file.

    Language is inferred from the filename: locale bundles named *zh* get the
    Chinese name, everything else gets the English one.
    """
    excludes = brand.get("exclude") or []
    found: dict[Path, str] = {}
    for entry in brand.get("text") or []:
        if "path" in entry:
            paths = [ROOT / entry["path"]]
        else:
            paths = [p for pat in expand_braces(entry["glob"]) for p in sorted(ROOT.glob(pat))]
        for path in paths:
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if _excluded(rel, excludes):
                continue
            found[path] = "zh" if re.search(r"(^|/)zh\.", rel) else "en"
    return sorted(found.items())


def uncovered_hits(brand: dict) -> list[str]:
    """Files in the sweep roots that still hold the brand but are NOT targeted.

    Guards against a silently empty glob -- a check that scans only the target
    list is vacuously green when the target list is wrong. It has to read every
    file type, not a whitelist of extensions: the first version only looked at
    .py/.ts/.tsx/.json/.less, and `desktop/portable/templates/README.txt` -- the
    first thing a customer sees after unzipping the portable package -- shipped
    with four occurrences of the old name while `--check` reported all clear.
    """
    covered = {p.relative_to(ROOT).as_posix() for p, _ in text_targets(brand)}
    excludes = brand.get("exclude") or []
    hits: list[str] = []
    for root in ("src/octop", "dashboard", "tests", "scripts", "desktop", "fnos", "docker"):
        for path in sorted((ROOT / root).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if "/node_modules/" in f"/{rel}" or "/dist/" in f"/{rel}":
                continue
            if rel in covered or _excluded(rel, excludes):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            text = _read(path)
            if text and TOKEN_RE.search(text):
                hits.append(rel)
    return hits
def apply_colors(brand: dict) -> int:
    """Point the default theme at the brand colour.

    Upstream ships 8 curated palettes plus a runtime-derived "custom" hex. We
    reuse `custom` rather than editing ~40 rose token lines, so the curated
    palettes stay selectable and the upstream diff stays two lines wide.
    """
    hexv = (brand.get("colors") or {}).get("brand")
    if not hexv:
        return 0
    changed = 0

    palettes = ROOT / "dashboard/src/styles/themePalettes.ts"
    if palettes.exists():
        text = palettes.read_text(encoding="utf-8")
        updated = re.sub(
            r'export const DEFAULT_PALETTE: ThemePalette = "[^"]*";',
            'export const DEFAULT_PALETTE: ThemePalette = "custom";',
            text,
        )
        updated = re.sub(
            r'export const DEFAULT_CUSTOM_COLOR = "[^"]*";',
            f'export const DEFAULT_CUSTOM_COLOR = "{hexv}";',
            updated,
        )
        if updated != text:
            palettes.write_text(updated, encoding="utf-8")
            print(f"  color themePalettes.ts -> {hexv}")
            changed += 1

    # CSS fallbacks and the pre-JS boot splash would otherwise flash rose.
    old = (brand.get("colors") or {}).get("upstream_hex") or "#e85d75"
    for path, _lang in text_targets(brand):
        text = _read(path)
        if text is None or old.lower() not in text.lower():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if ".test." in rel or rel.endswith(".spec.ts"):
            continue  # test files assert the curated palettes' real hexes
        if rel in {"dashboard/src/styles/themePalettes.ts", "dashboard/src/styles/theme-vars.css"}:
            continue  # keep the curated `rose` palette honest
        updated = re.sub(old, hexv, text, flags=re.IGNORECASE)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            print(f"  color   {rel}")
            changed += 1
    return changed


def apply_poses(brand: dict) -> int:
    """Render mascot poses from brand/assets/*.png.

    Only the animated .webp files are referenced by the dashboard; the .webm
    siblings ship but are never loaded, so animation is generated with PIL
    rather than requiring ffmpeg.
    """
    specs = brand.get("poses") or []
    if not specs:
        return 0
    import math

    from PIL import Image

    key_bg = bool((brand.get("assets") or {}).get("key_background"))
    changed = 0
    for spec in specs:
        src = ROOT / spec["src"]
        if not src.exists():
            print(f"  pose skip: {spec['src']} not found", file=sys.stderr)
            continue
        art = Image.open(src).convert("RGBA")
        side = min(art.size)
        art = art.crop(
            (
                (art.width - side) // 2,
                (art.height - side) // 2,
                (art.width + side) // 2,
                (art.height + side) // 2,
            )
        )
        if key_bg:
            art = key_background(art)

        dest = ROOT / spec["out"]
        buf = io.BytesIO()
        anim = spec.get("animate")
        if anim:
            w, h = spec["box"]
            base = art.copy()
            base.thumbnail((w, h), Image.LANCZOS)
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(base, ((w - base.width) // 2, (h - base.height) // 2), base)
            frames = []
            count = int(anim["frames"])
            for i in range(count):
                phase = math.sin(2 * math.pi * i / count)
                if anim["mode"] == "nod":
                    frame = canvas.rotate(
                        anim["amplitude"] * phase, resample=Image.BICUBIC, center=(w / 2, h)
                    )
                else:
                    frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    frame.paste(canvas, (0, int(anim["amplitude"] * phase)), canvas)
                frames.append(frame)
            frames[0].save(
                buf,
                "WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=int(anim["duration"]),
                loop=0,
            )
        else:
            size = spec["size"]
            art.resize((size, size), Image.LANCZOS).save(buf, "PNG")

        payload = buf.getvalue()
        if not dest.exists() or dest.read_bytes() != payload:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            print(f"  pose  {spec['out']}")
            changed += 1
    return changed


PRETTIER_EXTS = {".css", ".html", ".js", ".json", ".jsx", ".less", ".md", ".scss", ".ts", ".tsx"}


def _prettier() -> tuple[str, str] | None:
    """Locate node + the prettier CLI, or None if this box cannot format.

    A throwaway worktree (scripts/classify_owned.py) has no node_modules of its
    own, so fall back to the main checkout's -- both sides must produce the same
    bytes, or every formatted file gets misclassified as hand-edited.
    """
    node = shutil.which("node")
    if not node:
        return None
    rel = Path("dashboard") / "node_modules" / "prettier" / "bin" / "prettier.cjs"
    for base in (ROOT, _git_common_dir().parent if _git_common_dir() else ROOT):
        cli = base / rel
        if cli.is_file():
            return node, str(cli.resolve())
    return None


def _git_common_dir() -> Path | None:
    r = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True
    )
    if r.returncode:
        return None
    path = Path(r.stdout.strip())
    return path if path.is_absolute() else ROOT / path


def format_written() -> int:
    """Reflow the dashboard text files this run rewrote.

    Substituting "Octop" -> "zcagent" changes string lengths, which breaks
    prettier's line wrapping, and `npm run format:check` is a CI gate. Formatting
    has to belong to --apply: if it is a manual step it gets lost on the first
    regeneration after an upstream merge, and the gate goes red for no reason
    anyone can trace.
    """
    r = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    if r.returncode:
        return 0
    targets = [
        ROOT / p
        for p in r.stdout.split()
        if p.startswith("dashboard/") and Path(p).suffix.lower() in PRETTIER_EXTS
    ]
    if not targets:
        return 0
    cli = _prettier()
    if not cli:
        print("  format  SKIPPED (no node/prettier): run `npm run format` in dashboard/ before pushing")
        return 0
    proc = subprocess.run(
        [cli[0], cli[1], "--write", *(str(t) for t in targets)],
        cwd=ROOT / "dashboard",
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        print(f"  format  FAILED: {(proc.stderr or proc.stdout).strip()[:300]}")
        return 0
    wrote = len([line for line in proc.stdout.splitlines() if line.strip()])
    print(f"  format  prettier ran over {wrote} rewritten dashboard file(s)")
    return wrote


def cmd_apply(brand: dict) -> int:
    changed = 0
    for path, lang in text_targets(brand):
        rel = path.relative_to(ROOT)
        original = _read(path)
        if original is None:
            continue
        updated = transform(original, brand, lang)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print(f"  text  {rel}")
            changed += 1
    changed += apply_colors(brand)
    changed += apply_assets(brand)
    changed += apply_poses(brand)
    reflowed = format_written()
    print(f"rebrand: {changed} file(s) updated, {reflowed} reflowed by prettier")
    return 0


def key_background(img, tol: int = 26):
    """Make a flat-colour icon background transparent (corner pixel = bg)."""
    bg = img.getpixel((0, 0))[:3]
    pixels = list(img.getdata())
    out = []
    for px in pixels:
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            out.append((px[0], px[1], px[2], 0))
        else:
            out.append(px)
    keyed = img.copy()
    keyed.putdata(out)
    return keyed


FONT_CANDIDATES = {
    "bold": [
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ],
    "regular": [
        "C:/Windows/Fonts/msyh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ],
}


def find_font(brand: dict, kind: str) -> str:
    override = (brand.get("fonts") or {}).get(kind)
    candidates = ([override] if override else []) + FONT_CANDIDATES[kind]
    for path in candidates:
        if Path(path).exists():
            return path
    raise SystemExit(f"no CJK font found for lockup (looked for {kind}: {candidates})")


def build_lockup(mark_src, brand: dict, w: int, h: int, variant: str):
    """Compose mark + 中文名/英文名 into a horizontal logo (no AI text rendering)."""
    from PIL import Image, ImageDraw, ImageFont

    mark_h = h - 16
    mark = mark_src.resize((mark_h, mark_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(mark, (8, (h - mark_h) // 2), mark)

    brand_rgb = tuple(int(brand["colors"]["brand"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    ink = (245, 245, 248, 255) if variant == "light" else (31, 41, 55, 255)
    draw = ImageDraw.Draw(canvas)
    x = 8 + mark_h + 16
    zh_font = ImageFont.truetype(find_font(brand, "bold"), 30)
    en_font = ImageFont.truetype(find_font(brand, "regular"), 15)
    draw.text((x, 9), brand["name"]["zh"], font=zh_font, fill=ink)
    zh_w = draw.textlength(brand["name"]["zh"], font=zh_font)
    draw.text((x + zh_w + 10, 22), brand["name"]["en"], font=en_font, fill=brand_rgb + (255,))
    return canvas


def apply_assets(brand: dict) -> int:
    src = brand.get("assets", {}).get("icon")
    if not src:
        return 0
    icon = ROOT / src
    if not icon.exists():
        print(f"  assets skip: {src} not found", file=sys.stderr)
        return 0
    from PIL import Image

    base = Image.open(icon).convert("RGBA")
    side = min(base.size)
    x0 = (base.width - side) // 2
    y0 = (base.height - side) // 2
    base = base.crop((x0, y0, x0 + side, y0 + side))
    keyed = key_background(base) if brand["assets"].get("key_background") else base

    changed = 0
    for rel, spec in (brand.get("asset_map") or {}).items():
        dest = ROOT / rel
        source = base if spec.get("keep_bg") else keyed
        if "box" in spec:
            w, h = spec["box"]
            if spec.get("lockup"):
                out = build_lockup(source, brand, w, h, spec["lockup"])
            else:
                mark = source.copy()
                mark.thumbnail((h - 4, h - 4), Image.LANCZOS)
                canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                canvas.paste(mark, ((w - mark.width) // 2, (h - mark.height) // 2), mark)
                out = canvas
        else:
            out = source.resize((spec["size"], spec["size"]), Image.LANCZOS)
        if spec.get("svg"):
            buf = io.BytesIO()
            out.save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            s = spec["size"]
            body = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" '
                f'viewBox="0 0 {s} {s}"><image width="{s}" height="{s}" '
                f'href="data:image/png;base64,{b64}"/></svg>\n'
            )
            payload = body.encode()
        else:
            buf = io.BytesIO()
            out.save(buf, "PNG")
            payload = buf.getvalue()
        if not dest.exists() or dest.read_bytes() != payload:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            print(f"  asset {rel}")
            changed += 1
    return changed


def cmd_check(brand: dict) -> int:
    targets = text_targets(brand)
    if not targets:
        print("brand check FAILED: sweep matched zero files (broken glob?)")
        return 1
    leftovers = []
    for path, _lang in targets:
        text = _read(path)
        if text is None:
            continue
        hits = TOKEN_RE.findall(text)
        if hits:
            leftovers.append(f"  {path.relative_to(ROOT)}: {len(hits)}")
    gaps = uncovered_hits(brand)
    if leftovers or gaps:
        if leftovers:
            print(f"brand check FAILED: old brand still in {len(leftovers)} targeted file(s):")
            print("\n".join(leftovers[:20]))
        if gaps:
            print(f"brand check FAILED: {len(gaps)} file(s) hold the brand but are NOT swept:")
            print("\n".join(f"  {g}" for g in gaps[:20]))
        return 1
    print(f"brand check OK: {len(targets)} file(s) swept, no old brand left")
    return 0


def cmd_revert(brand: dict) -> int:
    paths = [str(p.relative_to(ROOT)) for p, _ in text_targets(brand)]
    paths += list(brand.get("asset_map") or {})
    subprocess.run(["git", "checkout", "--", *paths], cwd=ROOT, check=True)
    print(f"reverted {len(paths)} path(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--revert", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = ap.parse_args()

    brand = load_brand()
    if args.apply:
        return cmd_apply(brand)
    if args.check:
        return cmd_check(brand)
    if args.revert:
        return cmd_revert(brand)
    paths = [str(p.relative_to(ROOT)) for p, _ in text_targets(brand)]
    subprocess.run(["git", "diff", "--stat", "--", *paths], cwd=ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
