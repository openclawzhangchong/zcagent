#!/usr/bin/env python3
"""Upstream sync measurement.

Answers three questions a thin fork has to keep in view:

1. how far has upstream moved since the ref we last merged,
2. which upstream files do we deliberately modify (our "owned" set),
3. how big is the overlap -- the actual conflict surface.

Also guards two fork rules: we never add our own numbered migrations, and the
owned set is regenerated from git rather than hand-maintained.

Run from a checkout that has an `upstream` remote. Writes a markdown report to
--report (defaults to stdout) and exits non-zero when a trial merge conflicts or
a rule is broken, so CI goes red exactly when attention is needed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = ROOT / "brand" / "upstream-baseline.txt"
OWNED_FILE = ROOT / "brand" / "owned-files.txt"
STABLE_TAG = re.compile(r"^v\d+\.\d+\.\d+$")
MIGRATIONS = "src/octop/infra/db/migrations"


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def baseline_ref() -> str:
    if not BASELINE_FILE.exists():
        raise SystemExit(f"missing {BASELINE_FILE} -- record the upstream ref we last merged")
    return BASELINE_FILE.read_text(encoding="utf-8").strip().splitlines()[0]


def latest_stable_tag() -> str:
    tags = [t for t in git("tag", "--list", "v*").splitlines() if STABLE_TAG.match(t)]
    if not tags:
        raise SystemExit("no stable upstream tags found -- is the upstream remote fetched?")

    def key(tag: str) -> tuple[int, ...]:
        return tuple(int(p) for p in tag[1:].split("."))

    return max(tags, key=key)


def our_owned_upstream_files(base: str) -> list[str]:
    """The declared hand-edit surface, from brand/owned-files.txt.

    classify_owned.py derives that list by regenerating the baseline tree, so it
    is the authority. Fall back to a raw diff only if the file is missing.
    """
    if OWNED_FILE.exists():
        return [
            line.strip()
            for line in OWNED_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    diff = git("diff", "--name-only", f"{base}..HEAD").splitlines()
    upstream_files = set(git("ls-tree", "-r", "--name-only", base).splitlines())
    return sorted(set(diff) & upstream_files)


def migration_guard(base: str) -> list[str]:
    """Fail if we added a numbered migration of our own.

    Compared against our baseline, not the merge candidate: upstream keeps
    adding migrations itself, and those are theirs to merge, not a rule breach.
    """
    ours = set(git("ls-tree", "-r", "--name-only", "HEAD", "--", MIGRATIONS).splitlines())
    upstream = set(git("ls-tree", "-r", "--name-only", base, "--", MIGRATIONS).splitlines())
    return sorted(ours - upstream)


def trial_merge(candidate: str) -> list[str]:
    """Merge without committing, report conflicts, always roll back.

    Refuses to run on a dirty tree: rolling back uses reset --hard.
    """
    # reset --hard is part of the rollback, so refuse to run over real edits.
    # Untracked files are fine -- they are what CI reports get written into.
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked changes in the working tree -- commit or stash before a trial merge")
    result = subprocess.run(
        ["git", "merge", "--no-commit", "--no-ff", candidate],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    conflicts = [
        line.split(":", 1)[1].strip()
        for line in (result.stdout + result.stderr).splitlines()
        if line.startswith("CONFLICT")
    ]
    subprocess.run(["git", "merge", "--abort"], cwd=ROOT, capture_output=True)
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=ROOT, capture_output=True)
    return sorted(conflicts)


def report(base: str, candidate: str, owned: list[str], conflicts: list[str], extra: list[str]) -> str:
    ahead = int(git("rev-list", "--count", f"{base}..{candidate}"))
    lines = [
        "## Upstream sync measurement",
        "",
        f"- baseline (last merged): `{base}`",
        f"- candidate: `{candidate}` -- **{ahead} commits ahead of our baseline**",
        f"- upstream files we deliberately modify: **{len(owned)}**",
        f"- trial-merge conflicts: **{len(conflicts)}**",
        "",
    ]
    if conflicts:
        lines += ["### Conflicting files (resolve before merging for real)", ""]
        lines += [f"- `{f}`" for f in conflicts]
        lines.append("")
    if extra:
        lines += ["### Rule violations", ""] + [f"- {e}" for e in extra] + [""]
    lines += ["### Our owned upstream files", ""] + [f"- `{f}`" for f in owned]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", default=None, help="Upstream ref to trial-merge (default: newest stable tag)")
    ap.add_argument("--report", default=None, help="Write the markdown report to this file")
    args = ap.parse_args()

    # Best effort: the measurement is still valid against tags we already have,
    # and github.com transport is flaky enough that a failed fetch must not
    # become a red sync job.
    if subprocess.run(
        ["git", "fetch", "upstream", "--tags"], cwd=ROOT, capture_output=True, text=True
    ).returncode:
        print("warning: could not fetch upstream; measuring against local tags", file=sys.stderr)
    base = baseline_ref()
    candidate = args.candidate or latest_stable_tag()

    owned = our_owned_upstream_files(base)
    extra = []
    for path in migration_guard(base):
        extra.append(f"we added a migration of our own: `{path}` -- fold private data into a separate DB instead")

    # Our baseline can sit ahead of the newest stable tag (we started from main
    # while the last stable release was older). Nothing to merge yet then.
    if git_ok("merge-base", "--is-ancestor", candidate, base):
        conflicts = []
        markdown = (
            f"## Upstream sync measurement\n\n"
            f"- baseline: `{base}`\n- candidate `{candidate}` is already contained in the "
            "baseline -- nothing to merge yet\n"
            + (
                "\n### Rule violations\n" + "\n".join(f"- {e}" for e in extra) + "\n"
                if extra
                else ""
            )
        )
    else:
        conflicts = trial_merge(candidate)
        markdown = report(base, candidate, owned, conflicts, extra)
    if args.report:
        Path(args.report).write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)
    if conflicts or extra:
        print(f"sync-check FAILED: {len(conflicts)} conflict(s), {len(extra)} rule violation(s)", file=sys.stderr)
        return 1
    print(f"sync-check OK: {len(owned)} owned upstream file(s), trial merge clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
