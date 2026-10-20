"""Unit tests for the public-access (Cloudflare Tunnel) feature.

Kept deliberately offline: nothing here may reach github.com or trycloudflare,
because CI runs on networks that cannot. The live end-to-end proof is
``scripts/verify/tunnel_probe.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from octop.api.middleware.tunnel_guard import is_denied_over_tunnel
from octop.infra.tunnel import binary
from octop.infra.tunnel.manager import SETTINGS_KEY, TunnelManager, TunnelState


class _FakeSettingsRepo:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value


class _FakeServices:
    """Only what ``TunnelManager`` touches. ``user_manager`` deliberately absent:
    it lives on ``OctopServer``, not on ``SharedServices``."""

    def __init__(self) -> None:
        self.settings_repo = _FakeSettingsRepo()
        self.secret_repo = object()
        self.audit_repo = None  # type: ignore[assignment]
        self.config = None


# ── G5: what the tunnel may not reach ──────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/agents/ABC123/terminal/ws",
        "/api/agents/ABC123/terminal/context",
        "/api/browser/sessions",
        "/api/browser-stream/ws",
        "/api/desktop/screenshot",
        "/api/mobile/probe",
        "/api/filesystem/dirs",
        "/api/docs",
        "/api/openapi.json",
        "/api/admin/tls/apply",
        "/api/admin/backup/create",
    ],
)
def test_host_controlling_surfaces_are_denied_over_the_tunnel(path: str) -> None:
    assert is_denied_over_tunnel(path), path


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/auth/login",
        "/api/agents",
        "/api/agents/ABC123/chat/ws",
        "/api/threads",
        "/api/settings/captcha",
        # A sibling agent id must not be caught by the terminal pattern, and
        # "/api/browser" must not swallow a path that merely starts similar.
        "/api/agents/ABC123/chats",
        "/api/browsers",
        "/api/admin/tunnel",
    ],
)
def test_everyday_chat_surfaces_stay_allowed(path: str) -> None:
    assert not is_denied_over_tunnel(path), path


# ── pinned third-party binary ──────────────────────────────────────────────


def test_every_supported_platform_carries_a_digest_and_size() -> None:
    for key, art in binary._PLATFORM_ARTIFACTS.items():
        if art.sha256:
            assert art.bytes > 0, key
            assert len(art.sha256) == 64, key
            assert art.url.startswith("https://github.com/cloudflare/cloudflared/")


def test_platform_without_a_digest_is_reported_unsupported() -> None:
    assert binary.artifact_for("plan9-mips") is None
    assert not binary.is_ready("plan9-mips")


def test_is_ready_requires_the_verified_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(binary, "tunnel_dir", lambda: tmp_path)
    art = binary.artifact_for("windows-amd64")
    assert art is not None
    dest = tmp_path / "bin" / art.filename
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"not really cloudflared")
    assert not binary.is_ready("windows-amd64"), "a bare file must never count as verified"

    binary._marker_path(dest).write_text("0" * 64, encoding="utf-8")
    assert not binary.is_ready("windows-amd64"), "a stale digest must force a re-download"

    binary._marker_path(dest).write_text(art.sha256, encoding="utf-8")
    assert binary.is_ready("windows-amd64")


def test_download_that_does_not_match_the_release_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The digest check is the whole point of not bundling the binary."""
    monkeypatch.setattr(binary, "tunnel_dir", lambda: tmp_path)
    monkeypatch.setattr(
        binary, "platform_key", lambda: "windows-amd64"
    )  # CI runs on both, so pin the shape we assert on

    def fake_download(url: str, dest: Path, expect_bytes: int, timeout: int) -> None:
        dest.write_bytes(b"short")  # deliberately neither the size nor the bytes

    monkeypatch.setattr(binary, "_download", fake_download)
    with pytest.raises(RuntimeError):
        binary.ensure_binary()
    assert not list((tmp_path / "bin").glob("*.download")), "the temp file must not survive"


# ── state machine ──────────────────────────────────────────────────────────


def test_quick_tunnel_does_not_auto_resume_after_a_restart() -> None:
    """Auto-reconnecting would silently rot every link already sent to colleagues."""
    services = _FakeServices()
    services.settings_repo.set(
        SETTINGS_KEY,
        json.dumps({"enabled": True, "status": "live", "url": "https://x-y-z.trycloudflare.com"}),
    )
    manager = TunnelManager()
    manager.bind(services, 8088)  # type: ignore[arg-type]

    assert manager.state.enabled is False
    assert manager.state.url == ""
    assert manager.state.status == "stopped"
    assert "不会自动恢复" in manager.state.last_error
    # and it is persisted, so a second boot reads the same honest state
    assert services.settings_repo.get(SETTINGS_KEY) is not None
    assert json.loads(services.settings_repo.get(SETTINGS_KEY) or "{}")["status"] == "stopped"


def test_binding_twice_does_not_kill_a_live_tunnel() -> None:
    """Regression: every handler calls ``bind``, and a second load used to read
    the running tunnel's own ``enabled: true`` back and declare it stale."""
    manager = TunnelManager()
    manager.bind(_FakeServices(), 8088)  # type: ignore[arg-type]
    manager._state.enabled = True  # noqa: SLF001 - simulating a started tunnel
    manager._state.status = "live"  # noqa: SLF001
    manager._state.url = "https://a-b.trycloudflare.com"  # noqa: SLF001

    manager.bind(_FakeServices(), 8088)  # type: ignore[arg-type]

    assert manager.state.status == "live"
    assert manager.state.url == "https://a-b.trycloudflare.com"


def test_a_foreign_pid_is_never_trusted_as_ours() -> None:
    services = _FakeServices()
    services.settings_repo.set(SETTINGS_KEY, json.dumps({"enabled": False, "pid": 999999}))
    manager = TunnelManager()
    manager.bind(services, 8088)  # type: ignore[arg-type]
    assert manager.state.pid is None


def test_public_payload_withholds_the_consent_flag() -> None:
    state = TunnelState(url="https://a-b.trycloudflare.com", consent_ack=True, safe_mode=True)
    data: dict[str, Any] = state.public()
    assert "consent_ack" not in data
    assert data["url"] == "https://a-b.trycloudflare.com"
    assert data["safe_mode"] is True
