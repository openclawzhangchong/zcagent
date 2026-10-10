#!/usr/bin/env python3
"""Render the Windows client download page from release.json.

The page's whole value is that its version, byte counts, SHA256 and links match
the files it points at -- and hand-typed numbers are exactly how a download page
ends up lying. So the numbers live in one JSON file, the template holds `{{tokens}}`,
and `--from-github` rewrites the JSON from the Release API.

    python site/download/build.py --from-github   # refresh numbers, then render
    python site/download/build.py                 # render dist/ from release.json
    python site/download/build.py --check         # fail if dist/ is stale

Exit codes: 0 ok, 1 unresolved token / bad data, 2 dist is stale.
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
SRC = HERE / "src"
DIST = HERE / "dist"
DATA_FILE = HERE / "release.json"
TOKEN_RE = re.compile(r"\{\{([a-z0-9_.]+)\}\}")


def human(bytes_: int) -> str:
    return f"{bytes_ / 1048576:.1f} MiB（{bytes_:,} 字节）"


def short(digest: str) -> str:
    return f"{digest[:8]}…{digest[-6:]}"


def flatten(data: dict) -> dict[str, str]:
    out = {
        "version": data["version"],
        "tag": data["tag"],
        "date": data["date"],
        "tested_on": data["tested_on"],
        "runtime": data["runtime"],
        "portable_mib": f"{data['portable_extracted_mib']:,}",
        "release_url": data["release_url"],
        "repo_url": f"https://github.com/{data['repo']}",
        "changelog_url": f"https://github.com/{data['repo']}/blob/product/main/CHANGELOG.md",
        "issues_url": f"https://github.com/{data['repo']}/issues",
        "prev.version": data["previous"]["version"],
        "prev.tag": data["previous"]["tag"],
        "prev.reason": data["previous"]["reason"],
        "prev.release_url": f"https://github.com/{data['repo']}/releases/tag/{data['previous']['tag']}",
    }
    for kind in ("exe", "zip"):
        a = data["assets"][kind]
        out[f"{kind}.name"] = a["name"]
        out[f"{kind}.url"] = a["url"]
        out[f"{kind}.size"] = human(int(a["bytes"]))
        out[f"{kind}.bytes"] = f"{int(a['bytes']):,}"
        out[f"{kind}.sha"] = a["sha256"]
        out[f"{kind}.sha_short"] = short(a["sha256"])
    return out


def from_github(data: dict) -> dict:
    """Rewrite release.json from the GitHub Release API for the pinned tag."""
    api = f"https://api.github.com/repos/{data['repo']}/releases/tags/{data['tag']}"
    req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json"})
    token = None
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        token = token or __import__("os").environ.get(var)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        rel = json.loads(resp.read().decode("utf-8"))

    found = 0
    for asset in rel.get("assets", []):
        kind = "exe" if asset["name"].endswith(".exe") else "zip" if asset["name"].endswith(".zip") else None
        if kind not in data["assets"]:
            continue
        digest = (asset.get("digest") or "").removeprefix("sha256:")
        if not digest:
            raise SystemExit(f"{asset['name']}: the API returned no digest; refusing to publish a page without a hash")
        slot = data["assets"][kind]
        slot["name"] = asset["name"]
        slot["bytes"] = int(asset["size"])
        slot["sha256"] = digest
        slot["url"] = asset["browser_download_url"]
        found += 1
    if found != len(data["assets"]):
        raise SystemExit(f"expected {len(data['assets'])} assets on {data['tag']}, matched {found}")
    return data


def render(template: str, values: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise SystemExit(f"template uses {{{{{key}}}}} but release.json does not provide it")
        return values[key]

    out = TOKEN_RE.sub(sub, template)
    left = TOKEN_RE.findall(out)
    if left:
        raise SystemExit(f"unresolved tokens after render: {sorted(set(left))}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-github", action="store_true", help="refresh release.json from the Release API")
    ap.add_argument("--check", action="store_true", help="fail if dist/ does not match the template + data")
    args = ap.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if args.from_github:
        data = from_github(data)
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"release.json refreshed from {data['repo']} {data['tag']}")

    values = flatten(data)
    html = render((SRC / "index.html").read_text(encoding="utf-8"), values)

    expected = {"index.html": html}
    if args.check:
        for name, want in expected.items():
            got = (DIST / name).read_text(encoding="utf-8") if (DIST / name).is_file() else None
            if got != want:
                print(f"dist/{name} is stale -- run: python site/download/build.py", file=sys.stderr)
                return 2
        print("dist is up to date")
        return 0

    DIST.mkdir(exist_ok=True)
    (DIST / "index.html").write_text(html, encoding="utf-8")
    for asset in ("styles.css", "app.js"):
        shutil.copy2(SRC / asset, DIST / asset)
    if (SRC / "assets").is_dir():
        shutil.copytree(SRC / "assets", DIST / "assets", dirs_exist_ok=True)
    print(
        "wrote dist/  "
        f"exe {values['exe.bytes']} B {values['exe.sha_short']}  |  "
        f"zip {values['zip.bytes']} B {values['zip.sha_short']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
