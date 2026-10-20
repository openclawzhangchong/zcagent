"""Regression tests for mid-conversation skill visibility.

A conversation snapshots ``skills_metadata`` on its first turn and the harness
never re-scans it, so installing a skill left an already-open chat blind to it.
``octop.infra.skills.thread_state`` re-publishes the live pool into the thread
checkpoint, which is what the prompt renders from.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import SkillsMiddleware

from octop.infra.agents.manager import AgentManager
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.thread_state import (
    _MAX_TRACKED_THREADS,
    pool_signature,
    scan_skill_pool,
    sync_thread_skills,
)


def _write_skill(root: Path, slug: str, description: str = "Test skill") -> None:
    d = root / slug
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: {description}\n---\n\n# {slug}\n",
        encoding="utf-8",
    )


class _FakeGraph:
    def __init__(self) -> None:
        self.writes: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def aupdate_state(self, config: dict[str, Any], values: dict[str, Any]) -> None:
        self.writes.append((config, values))


def _fake_agent(tmp_path: Path, graph: _FakeGraph | None = None, disabled: frozenset[str] = frozenset()) -> SimpleNamespace:
    return SimpleNamespace(
        backend=FilesystemBackend(root_dir=str(tmp_path)),
        workspace=SimpleNamespace(skill_paths=lambda *, extra=None: ["/skills/"]),
        config=SimpleNamespace(skills_dir=None, skills_disabled=disabled),
        graph=graph if graph is not None else _FakeGraph(),
    )


async def _thread_skills(middleware: SkillsMiddleware, state: dict[str, Any]) -> list[str]:
    update = middleware.before_agent(state, None, {})  # type: ignore[arg-type]
    if update is not None:
        state.update(update)
    return sorted(str(s["name"]) for s in state["skills_metadata"])


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


async def test_a_disabled_skill_is_kept_out_of_the_prompted_pool(
    tmp_path: Path, skills_root: Path
) -> None:
    """``SkillFilterMiddleware`` renders too late to subtract, so filter here.

    Measured: with the real middleware order a disabled skill still reaches the
    system prompt, because ``SkillsMiddleware`` is the outermost layer and
    builds the section before the filter overrides state. The channel has to
    carry the truth instead.
    """
    _write_skill(skills_root, "alpha")
    _write_skill(skills_root, "beta")

    skills, _ = await scan_skill_pool(_fake_agent(tmp_path, disabled=frozenset({"beta"})))

    assert [s["name"] for s in skills] == ["alpha"]
    # And disabling changes what the model is shown, so it must trigger a write.
    enabled_pool, _ = await scan_skill_pool(_fake_agent(tmp_path))
    assert pool_signature(skills, []) != pool_signature(enabled_pool, [])


async def test_disabling_reaches_a_conversation_that_is_already_open(
    tmp_path: Path, skills_root: Path
) -> None:
    _write_skill(skills_root, "alpha")
    _write_skill(skills_root, "beta")
    graph = _FakeGraph()
    seen: dict[tuple[str, str], str] = {}
    await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t1", seen)

    disabled_agent = _fake_agent(tmp_path, graph, disabled=frozenset({"beta"}))
    assert await sync_thread_skills(disabled_agent, "A1", "t1", seen) is True
    written = graph.writes[-1][1]["skills_metadata"]
    assert [s["name"] for s in written] == ["alpha"]


async def test_scan_returns_the_live_pool(tmp_path: Path, skills_root: Path) -> None:
    _write_skill(skills_root, "alpha")
    _write_skill(skills_root, "beta")

    skills, errors = await scan_skill_pool(_fake_agent(tmp_path))

    assert sorted(s["name"] for s in skills) == ["alpha", "beta"]
    assert errors == []


async def test_scan_reports_an_unreadable_source_without_dropping_the_rest(
    tmp_path: Path, skills_root: Path
) -> None:
    _write_skill(skills_root, "alpha")
    agent = _fake_agent(tmp_path)
    agent.workspace = SimpleNamespace(skill_paths=lambda *, extra=None: ["/skills/", "/nope/"])

    skills, errors = await scan_skill_pool(agent)

    assert [s["name"] for s in skills] == ["alpha"]
    assert len(errors) == 1


async def test_a_skill_installed_mid_conversation_reaches_the_prompt(
    tmp_path: Path, skills_root: Path
) -> None:
    """The reported bug: market install invisible to a chat that was already open."""
    _write_skill(skills_root, "daily-hot-news")
    middleware = SkillsMiddleware(backend=FilesystemBackend(root_dir=str(tmp_path)), sources=["/skills/"])
    state: dict[str, Any] = {}

    # Turn 1 opens the conversation and freezes the pool.
    assert await _thread_skills(middleware, state) == ["daily-hot-news"]

    # The market installs a second skill while that conversation stays open.
    _write_skill(skills_root, "beatra")
    graph = _FakeGraph()
    seen: dict[tuple[str, str], str] = {}

    refreshed = await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t1", seen)

    assert refreshed is True
    config, values = graph.writes[0]
    assert config == {"configurable": {"thread_id": "t1"}}
    state.update(values)
    assert await _thread_skills(middleware, state) == ["beatra", "daily-hot-news"]
    assert "beatra" in middleware._format_skills_list(state["skills_metadata"])


async def test_next_turn_does_not_undo_the_republished_pool(
    tmp_path: Path, skills_root: Path
) -> None:
    """The freeze is what makes the fix stick: ``before_agent`` will not overwrite it."""
    _write_skill(skills_root, "alpha")
    middleware = SkillsMiddleware(backend=FilesystemBackend(root_dir=str(tmp_path)), sources=["/skills/"])
    state: dict[str, Any] = {}
    await _thread_skills(middleware, state)

    skills, _ = await scan_skill_pool(_fake_agent(tmp_path))
    state["skills_metadata"] = skills

    assert middleware.before_agent(state, None, {}) is None  # type: ignore[arg-type]
    assert [s["name"] for s in state["skills_metadata"]] == ["alpha"]


async def test_sync_is_a_no_op_until_the_pool_changes(tmp_path: Path, skills_root: Path) -> None:
    _write_skill(skills_root, "alpha")
    graph = _FakeGraph()
    seen: dict[tuple[str, str], str] = {}

    assert await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t1", seen) is True
    assert await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t1", seen) is False
    assert len(graph.writes) == 1

    _write_skill(skills_root, "beta")
    assert await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t1", seen) is True
    assert len(graph.writes) == 2


async def test_sync_treats_an_unknown_thread_as_stale(tmp_path: Path, skills_root: Path) -> None:
    """A restart must heal conversations that went stale under an earlier process."""
    _write_skill(skills_root, "alpha")
    graph = _FakeGraph()
    seen: dict[tuple[str, str], str] = {}
    await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t1", seen)

    fresh_process_copy = dict(seen)
    assert await sync_thread_skills(_fake_agent(tmp_path, graph), "A1", "t2", fresh_process_copy) is True


async def test_sync_skips_when_there_is_no_thread_or_no_writable_graph(
    tmp_path: Path, skills_root: Path
) -> None:
    _write_skill(skills_root, "alpha")
    seen: dict[tuple[str, str], str] = {}

    assert await sync_thread_skills(_fake_agent(tmp_path), "A1", "", seen) is False
    assert seen == {}

    agent = _fake_agent(tmp_path)
    agent.graph = object()
    assert await sync_thread_skills(agent, "A1", "t1", seen) is False
    assert seen == {}


def test_signature_tracks_content_not_order(skills_root: Path) -> None:
    _write_skill(skills_root, "alpha", description="first")
    _write_skill(skills_root, "beta")
    rows = [
        {"name": "beta", "description": "Test skill", "path": "/skills/beta/SKILL.md"},
        {"name": "alpha", "description": "first", "path": "/skills/alpha/SKILL.md"},
    ]
    swapped = list(reversed(rows))

    assert pool_signature(rows, []) == pool_signature(swapped, [])
    assert pool_signature(rows, []) != pool_signature(rows[:1], [])
    assert pool_signature(rows, []) != pool_signature(
        [{**rows[0], "description": "edited"}, rows[1]], []
    )
    assert pool_signature(rows, []) != pool_signature(rows, ["boom"])


def test_memo_stays_bounded() -> None:
    from octop.infra.skills.thread_state import _remember

    seen: dict[tuple[str, str], str] = {}
    for i in range(_MAX_TRACKED_THREADS + 50):
        _remember(seen, ("A", f"t{i}"), f"sig{i}")

    assert len(seen) == _MAX_TRACKED_THREADS
    assert ("A", "t0") not in seen
    assert ("A", f"t{_MAX_TRACKED_THREADS + 49}") in seen


async def test_manager_sync_never_breaks_the_turn(tmp_path: Path, skills_root: Path) -> None:
    seen: dict[tuple[str, str], str] = {}

    class _Stub:
        _skill_state_seen = seen

        def get_agent(self, agent_id: str):
            raise OctopError(ErrorCode.AGENT_NOT_RUNNING, "not running")

    await AgentManager._sync_thread_skill_state(_Stub(), "A1", "t1")  # type: ignore[arg-type]
    assert seen == {}

    class _BrokenAgent:
        backend = None
        graph = None

        def __getattr__(self, name: str):
            raise RuntimeError("backend exploded")

    class _Stub2:
        _skill_state_seen = seen

        def get_agent(self, agent_id: str):
            return _BrokenAgent()

    await AgentManager._sync_thread_skill_state(_Stub2(), "A1", "t1")  # type: ignore[arg-type]
    assert seen == {}
