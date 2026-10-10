"""决策留痕 — skill plugin (kind=skill).

Teaches the agent a decision-log workflow. It registers no callable tools: the
agent already has workspace file tools, and re-implementing file I/O here would
duplicate them and drift from whatever the harness does next release.
"""

from __future__ import annotations

from octop_harness.plugins import PluginContext


def setup(ctx: PluginContext) -> None:
    ctx.skills("skills")
