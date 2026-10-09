"""Runtime OEM branding overrides.

The build-time layer (``brand/brand.yaml`` + ``scripts/rebrand.py``) decides what
a fresh install ships as. This router is the per-deployment override a customer
admin can change afterwards -- product name, tagline, accent colour and logo --
without a rebuild. Values live in the settings KV, so no schema change.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from octop.api.deps import get_server, require_permission
from octop.infra.users.identity import User

router = APIRouter()

BRANDING_SETTING_KEY = "***"
MAX_LOGO_CHARS = 300_000
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingPayload(BaseModel):
    """Empty / absent fields mean "fall back to the build-time brand"."""

    name: str | None = Field(default=None, description="Product name for English locales.")
    name_zh: str | None = Field(default=None, description="Product name for Chinese locales.")
    tagline: str | None = Field(default=None, description="Subtitle shown on the login screen.")
    color: str | None = Field(default=None, description="Accent colour as #rrggbb.")
    logo_url: str | None = Field(
        default=None, description="Absolute https:// URL or an inline data:image/ URI."
    )

    @field_validator("color")
    @classmethod
    def _validate_color(cls, value: str | None) -> str | None:
        if value and not _HEX_COLOR.match(value):
            raise ValueError("color must be #rrggbb")
        return value

    @field_validator("logo_url")
    @classmethod
    def _validate_logo(cls, value: str | None) -> str | None:
        if not value:
            return value
        # Only https and inline images: no filesystem paths, so nothing can be
        # made to read back out of the host through an <img src>.
        if value.startswith("data:image/"):
            if len(value) > MAX_LOGO_CHARS:
                raise ValueError(f"inline logo exceeds {MAX_LOGO_CHARS} characters")
            return value
        if not value.startswith("https://"):
            raise ValueError("logo_url must be an https:// URL or a data:image/ URI")
        return value

    def cleaned(self) -> dict[str, str]:
        return {k: v for k, v in self.model_dump().items() if v}


@router.get("/branding", summary="Active branding overrides", response_model=BrandingPayload)
async def get_branding(server: Any = Depends(get_server)) -> BrandingPayload:
    raw = server.services.settings_repo.get(BRANDING_SETTING_KEY)
    if not raw:
        return BrandingPayload()
    return BrandingPayload(**json.loads(raw))


@router.put("/branding", summary="Replace branding overrides", response_model=BrandingPayload)
async def put_branding(
    payload: BrandingPayload,
    server: Any = Depends(get_server),
    _admin: User = Depends(require_permission("admin_console")),
) -> BrandingPayload:
    data = payload.cleaned()
    if data:
        server.services.settings_repo.set(
            BRANDING_SETTING_KEY, json.dumps(data, ensure_ascii=False)
        )
    else:
        server.services.settings_repo.delete(BRANDING_SETTING_KEY)
    return BrandingPayload(**data)
