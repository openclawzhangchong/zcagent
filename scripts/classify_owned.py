"""Classify our owned files as generated vs hand-edited, using the real pipeline.

Creates a throwaway worktree at the upstream baseline, runs `rebrand.py --apply`
there, then compares every file our branch touches against that regenerated
tree. Identical -> the tool produces it, so a merge conflict there is mechanical
(resolve to upstream and re-apply). Different -> it carries hand edits and is
the real conflict surface, recorded in brand/owned-files.txt.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("D:/otp/zcagent")
BASE = "0c5a46ab5f82e5ad9d1a56fa09b00e542f042fda"
PY = REPO / ".venv" / "Scripts" / "python.exe"


def run(*args: str, cwd: Path, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", **kw)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="zcagent-baseline-"))
    try:
        r = run("git", "worktree", "add", "--detach", str(tmp), BASE, cwd=REPO)
        if r.returncode:
            print("worktree add failed:", r.stderr)
            return 1

        # The baseline predates our tooling, so bring it in: pristine upstream
        # content + our brand config is exactly what a regeneration sees.
        shutil.copytree(REPO / "brand", tmp / "brand", dirs_exist_ok=True)
        shutil.copy2(REPO / "scripts" / "rebrand.py", tmp / "scripts" / "rebrand.py")

        r = run(str(PY), "scripts/rebrand.py", "--apply", cwd=tmp)
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:]
        print("apply in baseline worktree:", tail)
        if r.returncode:
            print("regeneration failed; refusing to classify on a broken tree")
            return 1

        owned = sorted(
            {
                p.replace("\\", "/")
                for p in run("git", "diff", "--name-only", f"{BASE}..HEAD", cwd=REPO)
                .stdout.split()
            }
        )
        generated, hand = [], []
        for rel in owned:
            ours, theirs = REPO / rel, tmp / rel
            same = ours.is_file() and theirs.is_file() and ours.read_bytes() == theirs.read_bytes()
            (generated if same else hand).append(rel)

        print(f"\nowned={len(owned)}  generated-by-tool={len(generated)}  hand-edited={len(hand)}")
        for f in hand:
            print("   hand:", f)

        out = REPO / "brand" / "owned-files.txt"
        out.write_text(
            "# Files carrying hand edits -- NOT produced by `rebrand.py --apply`.\n"
            "# These must survive a regeneration and are the real merge conflict\n"
            "# surface. The other ~260 files we touch are byte-identical to what\n"
            "# the tool regenerates from upstream, so a conflict in one of those is\n"
            "# mechanical: take upstream's side, then re-run --apply.\n"
            "# Regenerate this list with scripts/classify_owned.py.\n"
            + "\n".join(hand)
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {out}")
        return 0
    finally:
        run("git", "worktree", "remove", "--force", str(tmp), cwd=REPO)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
