"""Fetch a GitHub release asset with parallel ranged connections.

This box is throttled to ~50 KB/s *per connection* against GitHub's asset host,
so a single resumable curl takes an hour for a 234 MB artifact. Splitting the
remaining bytes across N connections multiplies throughput.

The existing partial file is kept as the prefix; only the tail is fetched, in
order-preserving part files, then concatenated. The result is checked against
the byte count and the SHA256 digest recorded in the release -- a tool's exit
code is never evidence that the bytes arrived.

    python scripts/verify/fetch_asset.py --out <file> --asset-id <id> --bytes <n> \
        --sha <hex> [--workers 8]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "openclawzhangchong/zcagent"
CHUNK = 1 << 20


def gh_token() -> str:
    out = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=False
    )
    return out.stdout.strip() or os.environ.get("GH_TOKEN", "")


def fetch_range(url: str, token: str, lo: int, hi: int, dest: Path) -> int:
    """Fetch [lo, hi] into dest (appending), resuming from whatever is there."""
    have = dest.stat().st_size if dest.exists() else 0
    want = hi - lo + 1
    if have >= want:
        return want
    start = lo + have
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream",
            "Range": f"bytes={start}-{hi}",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        # A 200 means the server ignored Range: the body is the whole asset from
        # byte 0, and appending it here would silently corrupt the part.
        if resp.status != 206:
            raise SystemExit(f"server answered {resp.status}, not 206 -- ranged fetch unsafe")
        with dest.open("ab") as fh:
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                fh.write(block)
    return dest.stat().st_size


def worker(url: str, token: str, lo: int, hi: int, dest: Path, attempts: int = 30) -> int:
    want = hi - lo + 1
    for _ in range(attempts):
        try:
            got = fetch_range(url, token, lo, hi, dest)
        except Exception as exc:  # noqa: BLE001 -- a stalled leg is normal here
            print(f"  part {dest.name}: {type(exc).__name__} {exc}", flush=True)
            got = dest.stat().st_size if dest.exists() else 0
        if got >= want:
            return want
    raise SystemExit(f"part {dest.name} stuck at {got}/{want}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(4 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--asset-id", type=int, required=True)
    ap.add_argument("--bytes", type=int, required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--repo",
        default=REPO,
        help="owner/name owning the release; also used for vendored third-party assets",
    )
    args = ap.parse_args()

    url = f"https://api.github.com/repos/{args.repo}/releases/assets/{args.asset_id}"
    token = gh_token()
    if not token:
        raise SystemExit("no gh token; run `gh auth login` or set GH_TOKEN")

    have = args.out.stat().st_size if args.out.exists() else 0
    if have == args.bytes:
        print(f"already complete: {args.out}")
    elif have > args.bytes:
        raise SystemExit(f"{args.out} is larger than the release says")
    else:
        parts_dir = args.out.with_suffix(args.out.suffix + ".parts")
        parts_dir.mkdir(parents=True, exist_ok=True)
        span = args.bytes - have
        size = max(1 << 20, span // args.workers)
        jobs = []
        offset = have
        index = 0
        while offset < args.bytes:
            lo, hi = offset, min(offset + size - 1, args.bytes - 1)
            jobs.append((lo, hi, parts_dir / f"part{index:03d}"))
            offset = hi + 1
            index += 1
        print(
            f"resuming at {have:,} of {args.bytes:,}: {len(jobs)} ranged connections",
            flush=True,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(worker, url, token, lo, hi, dest) for lo, hi, dest in jobs
            ]
            for fut in concurrent.futures.as_completed(futures):
                fut.result()
        with args.out.open("ab") as tail:
            for _lo, _hi, dest in jobs:
                tail.write(dest.read_bytes())
                dest.unlink()
        parts_dir.rmdir()

    got = args.out.stat().st_size
    if got != args.bytes:
        raise SystemExit(f"{args.out}: {got:,} bytes, release says {args.bytes:,}")
    actual = sha256(args.out)
    if actual != args.sha:
        raise SystemExit(f"SHA256 mismatch\n  expected {args.sha}\n  actual   {actual}")
    print(f"OK {args.out.name}  {got:,} B  {actual[:8]}…{actual[-6:]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
