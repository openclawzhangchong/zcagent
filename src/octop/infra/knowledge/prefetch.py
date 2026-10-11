"""Idle prefetch of the default knowledge-base embedding model.

A desktop user who opens 知识库设置 for the first time faces a 92 MB download
before anything works. Starting it in the background after boot removes that
wait, but the same code runs on air-gapped intranet boxes where all three
download sources are unreachable -- and there it must cost nothing and say
nothing. Hence the gates, cheapest first, in :func:`decide_prefetch`.

Deliberately Python-side only: the source race, the on-disk layout, the state
machine and the settings KV all live in the backend, and a second
implementation in the desktop shell would be this repo's third
"same rule written twice" incident.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from octop.infra.agents.providers.onnx_catalog import ONNX_PRESET_MODEL_IDS
from octop.infra.agents.providers.onnx_download import (
    build_download_candidates,
    probe_source,
)
from octop.infra.agents.providers.onnx_service import (
    DOWNLOAD_MANAGER,
    OnnxDownloadStatus,
    embedding_models_dir,
    is_model_downloaded,
)

logger = logging.getLogger(__name__)

DEFAULT_PREFETCH_MODEL = ONNX_PRESET_MODEL_IDS[0]
PREFETCH_STATE_KEY = "knowledge_onnx_prefetch"
PREFETCH_ATTEMPTS_KEY = "knowledge_onnx_prefetch_attempts"

# Kill switch for deployments with no outbound access. On by default: the
# offline kit passes an explicit "0" through its generated start script rather
# than relying on a probe that would burn four seconds on every boot.
PREFETCH_ENV = "OCTOP_KNOWLEDGE_MODEL_PREFETCH"

STARTUP_DELAY_S = 90.0
MAX_ATTEMPTS = 3
PROBE_TIMEOUT_S = 4.0
# Refuse to start if the volume cannot hold the model twice over: the download
# writes alongside the extracted files, and a half-written model is worse than
# none because it leaves the feature permanently unusable until someone deletes
# the directory by hand.
DISK_HEADROOM = 2.0

DONE = "done"
RUN = "run"
SKIP_DISABLED = "skip:disabled"
SKIP_ALREADY_DONE = "skip:already-done"
SKIP_ATTEMPTS = "skip:attempts-exhausted"
SKIP_PRESENT = "skip:model-present"
SKIP_DISK = "skip:disk-short"
SKIP_BUSY = "skip:download-busy"


def prefetch_enabled() -> bool:
    """Whether idle prefetch is allowed at all on this install."""
    raw = (os.environ.get(PREFETCH_ENV) or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _as_int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def decide_prefetch(
    *,
    enabled: bool,
    state: str,
    attempts: int,
    downloaded: bool,
    free_bytes: int,
    needed_bytes: int,
    download_busy: bool = False,
) -> str:
    """The whole policy, as a pure function so each gate is testable.

    Returns :data:`RUN` or a ``skip:*`` tag. Order matters: the checks that cost
    nothing come before the ones that touch the filesystem.
    """
    if not enabled:
        return SKIP_DISABLED
    if downloaded:
        return SKIP_PRESENT
    if state == DONE:
        return SKIP_ALREADY_DONE
    if attempts >= MAX_ATTEMPTS:
        return SKIP_ATTEMPTS
    if download_busy:
        return SKIP_BUSY
    if needed_bytes > 0 and free_bytes < needed_bytes * DISK_HEADROOM:
        return SKIP_DISK
    return RUN


def sources_reachable(model: str) -> bool:
    """Whether any download source answers. Air-gapped boxes fail all three."""
    candidates = build_download_candidates(model)
    for candidate in candidates:
        try:
            if probe_source(candidate.probe_url, timeout_s=PROBE_TIMEOUT_S) >= 0:
                return True
        except Exception as exc:  # any HTTP/network error means "not this one"
            logger.debug("ONNX prefetch probe failed for %s: %s", candidate.kind, exc)
    return False


async def _wait_for_download(model: str, timeout_s: float = 1800.0) -> str:
    """Follow the manager's state to a terminal value; it downloads on its own."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        status = DOWNLOAD_MANAGER.state.status
        if DOWNLOAD_MANAGER.state.model_name not in {"", model}:
            break
        if status is OnnxDownloadStatus.DONE:
            return DONE
        if status is OnnxDownloadStatus.FAILED:
            return "failed"
        await asyncio.sleep(2.0)
    return "abandoned"


async def prefetch_default_model(services: Any, *, delay_s: float = STARTUP_DELAY_S) -> str:
    """Try once to bring the default model down in the background.

    Never raises: this runs unattended at boot, and the failure mode we are
    protecting against is a noisy or expensive startup on a machine that simply
    has no internet.
    """
    outcome = "not-started"
    try:
        await asyncio.sleep(delay_s)
        settings = services.settings_repo
        model = DEFAULT_PREFETCH_MODEL
        needed = _expected_bytes(model)
        decision = decide_prefetch(
            enabled=prefetch_enabled(),
            state=str(settings.get(PREFETCH_STATE_KEY) or ""),
            attempts=_as_int(settings.get(PREFETCH_ATTEMPTS_KEY)),
            downloaded=is_model_downloaded(model),
            free_bytes=_free_bytes(),
            needed_bytes=needed,
            download_busy=DOWNLOAD_MANAGER.state.status is OnnxDownloadStatus.DOWNLOADING,
        )
        if decision != RUN:
            # A present model is the happy end state; record it so later boots
            # stop evaluating the gate chain at all.
            if decision == SKIP_PRESENT:
                settings.set(PREFETCH_STATE_KEY, DONE)
            logger.debug("ONNX prefetch %s", decision)
            return decision
        if not sources_reachable(model):
            settings.set(PREFETCH_ATTEMPTS_KEY, str(_bump(settings)))
            logger.info(
                "ONNX prefetch skipped: no download source reachable (the model "
                "will be offered again when you open knowledge-base settings)"
            )
            return "skip:unreachable"
        settings.set(PREFETCH_ATTEMPTS_KEY, str(_bump(settings)))
        await DOWNLOAD_MANAGER.start_download(model)
        outcome = await _wait_for_download(model)
        if outcome == DONE:
            settings.set(PREFETCH_STATE_KEY, DONE)
        return outcome
    except Exception as exc:  # never let a background nicety break a boot
        logger.info("ONNX prefetch gave up: %s", exc)
        return "error"


def _bump(settings: Any) -> int:
    attempts = _as_int(settings.get(PREFETCH_ATTEMPTS_KEY)) + 1
    return attempts


def _expected_bytes(model: str) -> int:
    from octop.infra.agents.providers.onnx_catalog import _FALLBACK_SIZE_GB

    size_gb = _FALLBACK_SIZE_GB.get(model, 0.1)
    return int(size_gb * 1024**3)


def _free_bytes() -> int:
    target = (
        embedding_models_dir().parent if embedding_models_dir().parent.exists() else Path.home()
    )
    try:
        return shutil.disk_usage(target).free
    except OSError:
        return 0
