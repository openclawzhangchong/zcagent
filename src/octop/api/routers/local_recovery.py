"""Password recovery for a single-owner install reached only from this machine.

The desktop client reuses ``~/.octop``, so installing over an older data
directory lands on a login page for an account the person never chose. The only
recovery path was a terminal command, which is the step ordinary users cannot do.

This endpoint grants exactly what ``octop user passwd`` already grants -- anyone
who can reach a loopback-bound server can already read and replace that same
SQLite file -- so it adds no privilege beyond the local filesystem trust the CLI
runs on. It therefore refuses to work anywhere that trust does not hold: a peer
that is not loopback, a server bound to a routable address (where a same-host
reverse proxy would otherwise present every remote caller as loopback), or an
install with more than one account, where resetting by username would let one
local person take over another's.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server
from octop.infra.users.password import validate_password_policy

router = APIRouter(tags=["auth"])

_LOOPBACK_BINDS = {"127.0.0.1", "::1", "localhost"}


def _peer_is_loopback(request: Request) -> bool:
    """The TCP peer, not ``resolve_client_ip`` -- that one honours X-Forwarded-For."""
    client = getattr(request, "client", None)
    host = (getattr(client, "host", None) or "").strip()
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _bound_to_loopback(server: Any) -> bool:
    bind = (getattr(server.services.config, "bind_host", "") or "").strip()
    return bind in _LOOPBACK_BINDS


class LocalResetBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


def _recovery_state(request: Request, server: Any) -> tuple[bool, str | None]:
    """``(available, username)`` -- the account name is only ever returned when
    the caller already proved it is this machine."""
    if not _peer_is_loopback(request) or not _bound_to_loopback(server):
        return False, None
    manager = server.user_manager
    if manager is None:
        return False, None
    accounts = manager.list()
    if len(accounts) != 1:
        return False, None
    return True, accounts[0].username


@router.get(
    "/local-recovery",
    summary="Whether this machine can reset its own account password",
)
async def local_recovery_status(
    request: Request, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Lets the login page offer the reset form instead of terminal instructions."""
    available, username = _recovery_state(request, server)
    return {"available": available, "username": username}


@router.post(
    "/local-reset",
    summary="Reset the only account's password, from this machine",
    responses={
        200: {"description": "Password replaced; the caller can now sign in."},
        403: {"description": "Not a loopback-bound single-account install."},
        404: {"description": "No such account."},
    },
)
async def local_reset(
    body: LocalResetBody, request: Request, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Replace the password of the sole local account without knowing the old one."""
    available, username = _recovery_state(request, server)
    if not available or username is None:
        raise HTTPException(status_code=403, detail="local_only")
    if body.username.strip() != username:
        raise HTTPException(status_code=404, detail="no_such_user")

    validate_password_policy(body.password)
    await server.user_manager.reset_password(username, body.password)
    # A lockout from forgotten attempts must not survive the reset -- clearing it
    # is the whole point of the call.
    await server.user_manager.unlock_login(username)
    return {"username": username, "reset": True}
