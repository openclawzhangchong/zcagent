"""HTTP surface for public access via Cloudflare Tunnel.

Admin-only on purpose: this is the switch that decides whether the machine is
reachable from the internet, so an ordinary employee account must not be able to
throw it. Every state change is written to ``audit_log``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.tunnel import binary
from octop.infra.tunnel.manager import get_manager
from octop.infra.users.password import validate_password_policy

router = APIRouter()

_CAPTCHA_OFF = ("", "none", "off")


class StartBody(BaseModel):
    # Re-typing the password is the only way to enforce the strength gate: the
    # stored value is a hash, so "is this admin's current password strong enough"
    # is unanswerable without the plaintext, and we refuse to guess. It also
    # proves the person clicking is the person who knows the credential.
    password: str = Field(..., min_length=1, max_length=256)
    safe_mode: bool = True
    consent_ack: bool = False


class PatchBody(BaseModel):
    safe_mode: bool


def _services(server: Any) -> Any:
    if server.services is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "服务尚未就绪")
    return server.services


def _port(server: Any) -> int:
    cfg = getattr(server.services, "config", None)
    return int(getattr(cfg, "port", 8088) or 8088)


def _docs_exposed(server: Any) -> bool:
    cfg = getattr(server.services, "config", None)
    return bool(getattr(cfg, "enable_api_docs", False))


def _captcha_active(services: Any) -> bool:
    from octop.infra.auth.captcha import current_env, load_view

    try:
        view = load_view(services.settings_repo, services.secret_repo, current_env())
    except Exception:  # noqa: BLE001 - a broken captcha config must not read as "safe"
        return False
    return str(view.get("active") or "").lower() not in _CAPTCHA_OFF


def _preflight(server: Any) -> list[dict[str, Any]]:
    """The checklist the UI shows before it will arm the switch."""
    services = _services(server)
    manager = get_manager()
    return [
        {
            "key": "accounts",
            "label_zh": "已完成首启并设置了管理员账号",
            "label_en": "Setup finished and an admin account exists",
            "ok": server.user_manager is not None and server.user_manager.count() > 0,
            "blocking": True,
            "fix_path": "",
        },
        {
            "key": "captcha",
            "label_zh": "登录验证码已开启",
            "label_en": "Login captcha is on",
            "ok": _captcha_active(services),
            "blocking": True,
            "fix_path": "/admin/security",
            "why_zh": "公网地址会被扫描。没有验证码，撞库可以慢慢试。",
            "why_en": "A public address gets scanned; without captcha, credential stuffing is unlimited.",
        },
        {
            "key": "api_docs",
            "label_zh": "接口文档未对外开放",
            "label_en": "API docs are not exposed",
            "ok": not _docs_exposed(server),
            "blocking": True,
            "fix_path": "/advanced-settings",
            "why_zh": "开着等于先给对方一份接口清单。",
            "why_en": "Leaving it on hands out an API inventory first.",
        },
        {
            "key": "platform",
            "label_zh": "当前平台支持公网访问组件",
            "label_en": "This platform supports the public-access component",
            "ok": binary.artifact_for() is not None,
            "blocking": True,
            "fix_path": "",
        },
        {
            "key": "safe_mode",
            "label_zh": "公网安全模式（隧道流量禁用终端 / 浏览器 / 远程桌面 / 本机文件）",
            "label_en": "Public-safe mode (terminal / browser / remote desktop / host files are blocked over the tunnel)",
            "ok": True,
            "blocking": False,
            "fix_path": "",
            "value": manager.state.safe_mode,
        },
    ]


@router.get("", summary="Public access status")
async def get_status(
    _: Any = Depends(require_permission("tunnel")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    services = _services(server)
    manager = get_manager()
    manager.bind(services, _port(server))
    return {
        "state": manager.state.public(),
        "running": manager.running,
        "binary_ready": binary.is_ready(),
        "binary_version": binary.CLOUDFLARED_VERSION,
        "local_port": _port(server),
    }


@router.get("/preflight", summary="What must be true before the tunnel may open")
async def get_preflight(
    _: Any = Depends(require_permission("tunnel")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    _services(server)
    items = _preflight(server)
    return {"items": items, "ready": all(i["ok"] or not i["blocking"] for i in items)}


@router.post("", summary="Open a public tunnel")
async def start(
    body: StartBody,
    user: Any = Depends(require_permission("tunnel")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    services = _services(server)
    manager = get_manager()
    manager.bind(services, _port(server))

    validate_password_policy(body.password)
    if await server.user_manager.authenticate(user.username, body.password) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "口令与当前账号不符")

    blocking = [i for i in _preflight(server) if i["blocking"] and not i["ok"]]
    if blocking:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "还有前置条件没满足：" + "、".join(str(i["label_zh"]) for i in blocking),
        )
    if not body.consent_ack:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "请先确认：开启后流量会经过 Cloudflare 的第三方边缘节点，"
            "这与「数据不出内网」的默认承诺不同。",
        )

    await manager.start(safe_mode=body.safe_mode, consent_ack=True)
    services.audit_repo.admin_event(
        "tunnel.start", target=user.username, payload=f"safe_mode={body.safe_mode}"
    )
    return {"state": manager.state.public()}


@router.post("/probe", summary="Re-check the public address")
async def probe(
    _: Any = Depends(require_permission("tunnel")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    services = _services(server)
    manager = get_manager()
    manager.bind(services, _port(server))
    result = await manager.reverify()
    return {"result": result, "state": manager.state.public()}


@router.delete("", summary="Close the public tunnel")
async def stop(
    user: Any = Depends(require_permission("tunnel")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    services = _services(server)
    manager = get_manager()
    await manager.stop()
    services.audit_repo.admin_event("tunnel.stop", target=user.username)
    return {"state": manager.state.public()}


@router.patch("", summary="Toggle public-safe mode")
async def patch(
    body: PatchBody,
    user: Any = Depends(require_permission("tunnel")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    services = _services(server)
    manager = get_manager()
    await manager.set_safe_mode(body.safe_mode)
    services.audit_repo.admin_event(
        "tunnel.safe_mode", target=user.username, payload=f"safe_mode={body.safe_mode}"
    )
    return {"state": manager.state.public()}
