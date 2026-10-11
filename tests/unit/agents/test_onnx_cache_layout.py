"""Tests for where a mirrored ONNX download is filed on disk.

The address matters as much as the bytes. A snapshot written under a readable
label (``cos-mirror``) is invisible to ``huggingface_hub``, which only reuses a
cache whose ``refs/<branch>`` holds a 40-character commit hash -- so loading the
model went back to needing huggingface.co reachable, and the installed client
answered "Could not load model ... from any source" while 94 MB of correct
weights sat in the cache. These tests pin the layout that actually loads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.providers.onnx_download import (
    LEGACY_COS_REVISION,
    hf_cache_snapshot_dir,
    mirror_revision,
    normalize_mirror_layout,
)

REPO = "Qdrant/bge-small-zh-v1.5"
FILES = ("config.json", "model_optimized.onnx", "tokenizer.json")


def test_mirror_revision_is_a_commit_shaped_hash() -> None:
    rev = mirror_revision(REPO)
    assert len(rev) == 40
    assert all(c in "0123456789abcdef" for c in rev)
    assert rev == mirror_revision(REPO)
    assert rev != mirror_revision("BAAI/bge-m3")


def test_snapshot_dir_is_what_the_hub_cache_lookup_resolves(tmp_path: Path) -> None:
    dest = hf_cache_snapshot_dir(tmp_path, REPO)
    repo_dir = tmp_path / "models--Qdrant--bge-small-zh-v1.5"
    assert dest == repo_dir / "snapshots" / mirror_revision(REPO)
    # Exact, not stripped: huggingface_hub 1.33 reads refs/main as-is, and one
    # trailing newline makes every file in the snapshot invisible to it.
    assert (repo_dir / "refs" / "main").read_text(encoding="utf-8") == dest.name


def test_normalize_drops_the_ref_newline_that_blinds_the_hub(tmp_path: Path) -> None:
    snapshot = hf_cache_snapshot_dir(tmp_path, REPO)
    (snapshot / "config.json").write_text("x", encoding="utf-8")
    ref = tmp_path / "models--Qdrant--bge-small-zh-v1.5" / "refs" / "main"
    ref.write_text(mirror_revision(REPO) + "\n", encoding="utf-8")

    assert normalize_mirror_layout(tmp_path) == 1
    assert ref.read_text(encoding="utf-8") == mirror_revision(REPO)
    assert snapshot.exists()
    assert normalize_mirror_layout(tmp_path) == 0


def test_snapshot_dir_refuses_a_label_the_hub_cannot_use(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        hf_cache_snapshot_dir(tmp_path, REPO, revision="cos-mirror")


def _seed_legacy_cache(root: Path) -> Path:
    snapshot = root / "models--Qdrant--bge-small-zh-v1.5" / "snapshots" / LEGACY_COS_REVISION
    snapshot.mkdir(parents=True)
    for name in FILES:
        (snapshot / name).write_text("x", encoding="utf-8")
    return snapshot


def test_normalize_moves_old_layouts_and_keeps_every_file(tmp_path: Path) -> None:
    legacy = _seed_legacy_cache(tmp_path)

    assert normalize_mirror_layout(tmp_path) == 1
    assert not legacy.exists()
    moved = tmp_path / "models--Qdrant--bge-small-zh-v1.5" / "snapshots" / mirror_revision(REPO)
    assert sorted(p.name for p in moved.iterdir()) == sorted(FILES)
    assert (tmp_path / "models--Qdrant--bge-small-zh-v1.5" / "refs" / "main").exists()


def test_normalize_is_idempotent_and_leaves_good_caches_alone(tmp_path: Path) -> None:
    _seed_legacy_cache(tmp_path)
    assert normalize_mirror_layout(tmp_path) == 1
    healthy = hf_cache_snapshot_dir(tmp_path, "BAAI/bge-m3")
    (healthy / "model_optimized.onnx").write_text("x", encoding="utf-8")

    assert normalize_mirror_layout(tmp_path) == 0
    assert healthy.exists()


def test_normalize_prefers_the_hashed_copy_when_both_exist(tmp_path: Path) -> None:
    legacy = _seed_legacy_cache(tmp_path)
    (legacy / "only-in-legacy.txt").write_text("x", encoding="utf-8")
    hashed = hf_cache_snapshot_dir(tmp_path, REPO)
    (hashed / "config.json").write_text("newer", encoding="utf-8")

    assert normalize_mirror_layout(tmp_path) == 1
    assert not legacy.exists()
    assert (hashed / "config.json").read_text(encoding="utf-8") == "newer"
    assert not (hashed / "only-in-legacy.txt").exists()


def test_normalize_on_a_missing_cache_dir(tmp_path: Path) -> None:
    assert normalize_mirror_layout(tmp_path / "nope") == 0
