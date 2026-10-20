"""Strip the host-controlling surfaces from requests that arrive over the tunnel.

The product's promise is "runs on your own machine" (``README.md``), and the
agent can already reach a shell, a browser, a remote desktop and the host
filesystem. Those are fine on loopback and indefensible on a public URL, so the
tunnel ships with this guard on by default: a request that came through
Cloudflare may chat, browse its own threads and read settings it is permitted to
read, but cannot drive the machine.

Why a header and not a socket property: cloudflared connects *out* to the edge,
so every tunneled request reaches us from ``127.0.0.1`` and the peer address
carries no information. Cloudflare stamps ``Cf-Connecting-Ip`` on every request
it forwards, which is the only usable signal.

The spoofing direction is deliberately one-way. A local process can add
``Cf-Connecting-Ip`` to its own request, but the only effect is that it gets
treated as remote and loses access -- fail-closed. A remote user cannot *remove*
the header the edge inserted, so they cannot escape the restriction.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

TUNNEL_MARKER_HEADER = "cf-connecting-ip"

#: Whole prefixes that never cross the tunnel.
DENIED_PREFIXES: tuple[str, ...] = (
    "/api/browser",
    "/api/browser-stream",
    "/api/desktop",
    "/api/mobile",
    "/api/filesystem",
    "/api/docs",
    "/api/openapi.json",
)

#: Per-agent host shell, and the terminal's websocket.
DENIED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/agents/[^/]+/terminal(/|$)"),
    re.compile(r"^/api/admin/(tls|update|backup)(/|$)"),
)

_INSTALL_ATTR = "_octop_tunnel_guard_installed"


def _under(path: str, prefix: str) -> bool:
    """True when *path* is *prefix* or something below it.

    Plain ``startswith`` would also deny ``/api/browsers`` for the ``/api/browser``
    entry, so compare on segment boundaries.
    """
    return path == prefix or path.startswith(prefix + "/")


def is_denied_over_tunnel(path: str) -> bool:
    if any(_under(path, p) for p in DENIED_PREFIXES):
        return True
    return any(p.match(path) for p in DENIED_PATTERNS)


def install(app: Any, server: Any) -> None:
    """Guard is inert until a tunnel is both up and in safe mode."""
    if getattr(app, _INSTALL_ATTR, False):
        return
    setattr(app, _INSTALL_ATTR, True)

    @app.middleware("http")  # type: ignore[untyped-decorator]
    async def _guard(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        from octop.infra.tunnel.manager import get_manager

        state = get_manager().state
        active = state.enabled and state.safe_mode and bool(state.url)
        if not active or not request.headers.get(TUNNEL_MARKER_HEADER):
            return await call_next(request)
        path = request.url.path
        if not is_denied_over_tunnel(path):
            return await call_next(request)
        user = getattr(request.state, "octop_user", None)
        log.warning(
            "tunnel: refused %s for %s over public access",
            path,
            getattr(user, "username", "anonymous"),
        )
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "TUNNEL_RESTRICTED",
                    "message": "这个功能在公网访问期间被禁用。请在本机或内网地址上关闭"
                    "「公网安全模式」后再使用。",
                    "details": {"path": path},
                }
            },
        )
