"""Guard tests for the loopback-only password recovery endpoint.

The endpoint replaces a password with no authentication at all, so every case
here is an attempt to make it apply where it should not.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from octop.api.routers.local_recovery import (
    LocalResetBody,
    local_recovery_status,
    local_reset,
)
from octop.infra.errors import ErrorCode, OctopError


class _Manager:
    def __init__(self, usernames: list[str]) -> None:
        self._users = [SimpleNamespace(username=name) for name in usernames]
        self.reset: list[tuple[str, str]] = []
        self.unlocked: list[str] = []

    def list(self) -> list[Any]:
        return list(self._users)

    async def reset_password(self, username: str, new: str) -> None:
        self.reset.append((username, new))

    async def unlock_login(self, username: str) -> None:
        self.unlocked.append(username)


def _request(peer: str | None) -> SimpleNamespace:
    client = None if peer is None else SimpleNamespace(host=peer)
    return SimpleNamespace(client=client)


def _server(peer: str, usernames: list[str], bind: str = "127.0.0.1") -> tuple[Any, _Manager]:
    manager = _Manager(usernames)
    return (
        SimpleNamespace(
            user_manager=manager,
            services=SimpleNamespace(config=SimpleNamespace(bind_host=bind)),
        ),
        manager,
    )


def _body(username: str = "admin", password: str = "Passw0rd123") -> LocalResetBody:
    return LocalResetBody(username=username, password=password)


@pytest.mark.asyncio
async def test_remote_peer_is_refused() -> None:
    server, manager = _server("admin", ["admin"])
    with pytest.raises(HTTPException) as exc:
        await local_reset(_body(), _request("203.0.113.9"), server)
    assert exc.value.status_code == 403
    assert manager.reset == []


@pytest.mark.asyncio
async def test_forwarded_header_cannot_make_a_remote_peer_local() -> None:
    """The guard reads the TCP peer, so ``X-Forwarded-For: 127.0.0.1`` does not help."""
    server, manager = _server("admin", ["admin"])
    request = _request("203.0.113.9")
    request.headers = {"x-forwarded-for": "127.0.0.1"}  # type: ignore[attr-defined]
    with pytest.raises(HTTPException) as exc:
        await local_reset(_body(), request, server)
    assert exc.value.status_code == 403
    assert manager.reset == []


@pytest.mark.asyncio
async def test_routable_bind_is_refused_even_from_loopback() -> None:
    """Behind a same-host proxy every remote caller arrives from loopback."""
    server, manager = _server("admin", ["admin"], bind="0.0.0.0")
    with pytest.raises(HTTPException) as exc:
        await local_reset(_body(), _request("127.0.0.1"), server)
    assert exc.value.status_code == 403
    assert manager.reset == []


@pytest.mark.asyncio
async def test_multi_user_install_is_refused() -> None:
    server, manager = _server("admin", ["admin", "bob"])
    with pytest.raises(HTTPException) as exc:
        await local_reset(_body(), _request("127.0.0.1"), server)
    assert exc.value.status_code == 403
    assert manager.reset == []


@pytest.mark.asyncio
async def test_missing_peer_socket_is_refused() -> None:
    server, _ = _server("admin", ["admin"])
    with pytest.raises(HTTPException) as exc:
        await local_reset(_body(), _request(None), server)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_happy_path_resets_and_clears_the_lockout() -> None:
    server, manager = _server("admin", ["admin"])
    result = await local_reset(_body(password="N3wSecret99"), _request("::1"), server)
    assert result == {"username": "admin", "reset": True}
    assert manager.reset == [("admin", "N3wSecret99")]
    # A lockout left by the forgotten-password attempts must not survive.
    assert manager.unlocked == ["admin"]


@pytest.mark.asyncio
async def test_other_username_is_not_reset() -> None:
    server, manager = _server("admin", ["admin"])
    with pytest.raises(HTTPException) as exc:
        await local_reset(_body(username="attacker"), _request("127.0.0.1"), server)
    assert exc.value.status_code == 404
    assert manager.reset == []


@pytest.mark.asyncio
async def test_weak_password_reaches_the_shared_policy() -> None:
    """The OctopError propagates so the dashboard renders its existing localized code."""
    server, manager = _server("admin", ["admin"])
    with pytest.raises(OctopError) as exc:
        await local_reset(_body(password="short"), _request("127.0.0.1"), server)
    assert exc.value.code is ErrorCode.PASSWORD_TOO_WEAK
    assert manager.reset == []


@pytest.mark.asyncio
async def test_status_offers_recovery_only_where_reset_works() -> None:
    server, _ = _server("admin", ["admin"])
    assert await local_recovery_status(_request("127.0.0.1"), server) == {
        "available": True,
        "username": "admin",
    }
    remote, _ = _server("admin", ["admin"])
    assert await local_recovery_status(_request("203.0.113.9"), remote) == {
        "available": False,
        "username": None,
    }
    shared, _ = _server("admin", ["admin", "bob"])
    assert await local_recovery_status(_request("127.0.0.1"), shared) == {
        "available": False,
        "username": None,
    }


def test_body_bounds() -> None:
    with pytest.raises(ValidationError):
        LocalResetBody(username="", password="Passw0rd123")
    with pytest.raises(ValidationError):
        LocalResetBody(username="admin", password="")
