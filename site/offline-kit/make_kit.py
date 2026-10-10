#!/usr/bin/env python3
"""Assemble the offline delivery kit (USB / intranet share) for a release.

The kit is generated, never assembled by hand: a folder someone carries to a
customer must not contain a half-downloaded installer or a stale checksum. Every
artifact is SHA256-verified against the digest recorded in
`site/download/release.json` (which `build.py --from-github` pulls from the
Release API), and the build aborts on any mismatch.

    python site/offline-kit/make_kit.py                      # download + verify
    python site/offline-kit/make_kit.py --local D:\\otp\\deliver   # reuse files already fetched
    python site/offline-kit/make_kit.py --out \\\\host\\share\\zcagent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE.parent / "download" / "release.json"
CHUNK = 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, expect_bytes: int) -> None:
    """Download with resume, then confirm the byte count.

    `gh release download` has returned success on a 37%-complete file on this
    project, so a tool's exit code is not evidence that bytes arrived.
    """
    for attempt in range(1, 21):
        have = dest.stat().st_size if dest.exists() else 0
        if have == expect_bytes:
            return
        cmd = [
            "curl",
            "-sSL",
            "--connect-timeout",
            "25",
            "--max-time",
            "900",
            "-C",
            "-",
            "-o",
            str(dest),
            url,
        ]
        subprocess.run(cmd, check=False)
        if dest.exists() and dest.stat().st_size == expect_bytes:
            return
        print(f"  attempt {attempt}: {have}/{expect_bytes} bytes")
    raise SystemExit(f"download never completed: {url}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", type=Path, help="directory with the artifacts already downloaded")
    ap.add_argument("--out", type=Path, default=HERE / "dist")
    args = ap.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    kit = args.out / f"zcagent-{data['version']}-windows-offline-kit"
    kit.mkdir(parents=True, exist_ok=True)

    lines = []
    for asset in data["assets"].values():
        name, size, digest, url = asset["name"], int(asset["bytes"]), asset["sha256"], asset["url"]
        dest = kit / name
        if not dest.exists():
            src = (args.local / name) if args.local else None
            if src and src.exists():
                shutil.copy2(src, dest)
            else:
                print(f"fetching {name} ...")
                fetch(url, dest, size)

        got = dest.stat().st_size
        if got != size:
            raise SystemExit(f"{name}: {got} bytes on disk, release says {size}")
        actual = sha256(dest)
        if actual != digest:
            dest.unlink(missing_ok=True)
            raise SystemExit(
                f"{name}: SHA256 mismatch\n  expected {digest}\n  actual   {actual}\n"
                f"refusing to ship a kit whose installer does not match the release"
            )
        print(f"verified {name}  {size:,} B  {digest[:8]}…{digest[-6:]}")
        lines.append(f"{digest}  {name}")

    (kit / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(HERE / "guide.md", kit / "guide.md")
    (kit / "README-FOR-OPS.txt").write_text(
        "先读 guide.md。第一步永远是 Get-FileHash 对 SHA256SUMS.txt。\n"
        f"版本 {data['version']}（tag {data['tag']}），下载页 {data.get('site_url', data['release_url'])}\n",
        encoding="utf-8",
    )
    print(f"\nkit ready: {kit}")
    for item in sorted(kit.iterdir()):
        print(f"  {item.stat().st_size:>12,} B  {item.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
