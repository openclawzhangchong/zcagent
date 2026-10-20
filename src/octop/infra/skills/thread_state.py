"""Re-publish an agent's live skill pool into a conversation's checkpoint state.

``deepagents.SkillsMiddleware.before_agent`` fills the ``skills_metadata``
channel once per thread and then skips whenever the channel already exists.
LangGraph checkpoints that channel, and the harness even externalizes it as a
content-addressed blob, so the pool a conversation saw on its first turn is
what that conversation keeps seeing — installing a skill from the market, or
writing one into the workspace by hand, cannot reach it.

``SkillFilterMiddleware`` cannot rescue this either. It sits *after*
``SkillsMiddleware`` in the stack, and the first middleware is the outermost
layer, so its ``request.override(state=...)`` runs after the skills section has
already been rendered. Measured: with ``skills_disabled={"beta"}`` the model
still sees ``beta``. Its filesystem/``execute`` blocking does work, because
tool calls go through ``wrap_tool_call``.

So the channel itself has to carry the truth. This module rescans the pool
before a turn, drops the disabled entries, and overwrites the channel when the
result changed. The overwrite is what the prompt renders from, so replacing it
is enough — the freeze then works in our favour and nothing re-scans mid-turn.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any

from deepagents.middleware.skills import SkillsMiddleware
from octop_harness.skills.catalog import skill_identity_keys

if TYPE_CHECKING:
    from octop_harness import HarnessAgent

logger = logging.getLogger(__name__)

_MAX_TRACKED_THREADS = 4096


async def scan_skill_pool(agent: HarnessAgent) -> tuple[list[dict[str, Any]], list[str]]:
    """Return the skills this agent should show the model, with load errors.

    Uses the agent's own backend and source roots, so path spellings stay
    identical to what ``SkillsMiddleware`` writes during a fresh thread. The
    disabled set is applied here rather than left to ``SkillFilterMiddleware``,
    which cannot influence the rendered prompt (see the module docstring).
    """
    middleware = SkillsMiddleware(
        backend=agent.backend,
        sources=agent.workspace.skill_paths(extra=agent.config.skills_dir),
    )
    # An empty state is the one input that makes before_agent scan instead of
    # short-circuit; runtime/config are unused by the hook.
    update = await middleware.abefore_agent({}, None, {})  # type: ignore[arg-type]
    skills = list((update or {}).get("skills_metadata") or [])
    errors = list((update or {}).get("skills_load_errors") or [])
    disabled = frozenset(str(x) for x in (agent.config.skills_disabled or ()))
    if disabled:
        skills = [skill for skill in skills if not (skill_identity_keys(skill) & disabled)]
    return skills, errors


def pool_signature(skills: list[dict[str, Any]], errors: list[str]) -> str:
    """Stable digest of what the model would be shown for this pool.

    Covers identity plus the rendered text, so a renamed skill, an edited
    description, a newly disabled skill and a newly unreadable skill root all
    change the digest, while a reordered scan does not.
    """
    rows = sorted((str(s.get("name")), str(s.get("description")), str(s.get("path"))) for s in skills)
    payload = json.dumps([rows, sorted(errors)], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _remember(seen: dict[tuple[str, str], str], key: tuple[str, str], signature: str) -> None:
    seen[key] = signature
    while len(seen) > _MAX_TRACKED_THREADS:
        seen.pop(next(iter(seen)), None)


async def sync_thread_skills(
    agent: HarnessAgent,
    agent_id: str,
    thread_id: str,
    seen: dict[tuple[str, str], str],
) -> bool:
    """Refresh *thread_id*'s skill channel when the pool no longer matches.

    Returns ``True`` when the checkpoint was rewritten. *seen* is the caller's
    (agent, thread) → signature memo; an unknown thread is treated as stale so
    a restart also heals conversations that went stale under an earlier process.
    """
    if not thread_id:
        return False
    graph = getattr(agent, "graph", None)
    if graph is None or not hasattr(graph, "aupdate_state"):
        return False

    skills, errors = await scan_skill_pool(agent)
    key = (agent_id, thread_id)
    signature = pool_signature(skills, errors)
    if seen.get(key) == signature:
        return False

    await graph.aupdate_state(  # type: ignore[attr-defined]
        {"configurable": {"thread_id": thread_id}},
        {"skills_metadata": skills, "skills_load_errors": errors},
    )
    _remember(seen, key, signature)
    logger.info(
        "Skill pool refreshed for thread %s (agent %s): %d skill(s), %d load error(s)",
        thread_id,
        agent_id,
        len(skills),
        len(errors),
    )
    return True


__all__ = ["pool_signature", "scan_skill_pool", "sync_thread_skills"]
