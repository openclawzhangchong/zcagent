"""Unit tests for the runtime OEM branding override router.

The interesting surface is the ``logo_url`` guard: it is written by an admin but
rendered by every visitor's browser, so a filesystem path in there would turn a
branding setting into a way to read the host back out.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from octop.api.routers.branding import (
    BRANDING_SETTING_KEY,
    MAX_LOGO_CHARS,
    BrandingPayload,
    get_branding,
    put_branding,
)


class _SettingsRepo:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.deleted: list[str] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.store.pop(key, None)


@pytest.fixture()
def server() -> SimpleNamespace:
    return SimpleNamespace(services=SimpleNamespace(settings_repo=_SettingsRepo()))


@pytest.mark.asyncio
async def test_get_returns_empty_when_nothing_is_configured(server: SimpleNamespace) -> None:
    payload = await get_branding(server)
    assert payload.name is None
    assert payload.logo_url is None


@pytest.mark.asyncio
async def test_put_round_trips_through_the_settings_kv(server: SimpleNamespace) -> None:
    stored = await put_branding(
        BrandingPayload(name="Other", name_zh="别家", color="#0F766E"), server, None
    )
    assert stored.name == "Other"
    raw = server.services.settings_repo.store[BRANDING_SETTING_KEY]
    assert json.loads(raw)["name_zh"] == "别家"
    again = await get_branding(server)
    assert again.name_zh == "别家"
    assert again.color == "#0F766E"


@pytest.mark.asyncio
async def test_put_of_an_empty_payload_clears_the_row(server: SimpleNamespace) -> None:
    await put_branding(BrandingPayload(name="Other"), server, None)
    cleared = await put_branding(BrandingPayload(), server, None)
    assert cleared.model_dump() == {
        "name": None,
        "name_zh": None,
        "tagline": None,
        "color": None,
        "logo_url": None,
        "download_url": None,
    }
    assert server.services.settings_repo.deleted == [BRANDING_SETTING_KEY]
    assert server.services.settings_repo.store == {}


@pytest.mark.parametrize(
    "value",
    [
        "file:///etc/passwd",
        "/etc/passwd",
        "../../.octop/octop.db",
        "http://unencrypted.example/logo.png",
        "data:text/html,<script>alert(1)</script>",
        "javascript:alert(1)",
    ],
)
def test_logo_url_rejects_anything_that_is_not_https_or_an_inline_image(value: str) -> None:
    with pytest.raises(ValidationError):
        BrandingPayload(logo_url=value)


@pytest.mark.parametrize(
    "value",
    ["https://cdn.example.com/a.png", "data:image/png;base64,iVBORw0KGgo="],
)
def test_logo_url_accepts_https_and_inline_images(value: str) -> None:
    assert BrandingPayload(logo_url=value).logo_url == value


def test_inline_logo_is_size_capped() -> None:
    prefix = "data:image/png;base64,"
    fits = prefix + "A" * (MAX_LOGO_CHARS - len(prefix))
    assert BrandingPayload(logo_url=fits).logo_url == fits
    with pytest.raises(ValidationError):
        BrandingPayload(logo_url=fits + "A")


@pytest.mark.parametrize("value", ["#3D5A80", "#0f766e"])
def test_color_accepts_hex(value: str) -> None:
    assert BrandingPayload(color=value).color == value


@pytest.mark.parametrize("value", ["3D5A80", "red", "#fff", "#3D5A800", "var(--brand)"])
def test_color_rejects_anything_that_is_not_rrggbb(value: str) -> None:
    with pytest.raises(ValidationError):
        BrandingPayload(color=value)


@pytest.mark.parametrize("value", ["https://dl.example.com/win", "http://10.0.0.8/zcagent/"])
def test_download_url_accepts_http_for_intranet_mirrors(value: str) -> None:
    """Unlike logo_url, this field is clicked as a link, not loaded as a
    subresource -- so plain http on an intranet is the normal case."""
    assert BrandingPayload(download_url=value).download_url == value


@pytest.mark.parametrize(
    "value",
    ["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "file:///c:/", "//x/y"],
)
def test_download_url_rejects_executable_or_relative_schemes(value: str) -> None:
    with pytest.raises(ValidationError):
        BrandingPayload(download_url=value)


@pytest.mark.asyncio
async def test_download_url_round_trips_and_persists_with_the_rest(
    server: SimpleNamespace,
) -> None:
    await put_branding(
        BrandingPayload(name="Other", download_url="http://intranet/dl"), server, None
    )
    stored = json.loads(server.services.settings_repo.store[BRANDING_SETTING_KEY])
    assert stored == {"name": "Other", "download_url": "http://intranet/dl"}
    assert (await get_branding(server)).download_url == "http://intranet/dl"


def test_blank_fields_are_dropped_so_a_partial_edit_keeps_the_rest() -> None:
    payload = BrandingPayload(name="Other", name_zh="", tagline=None)
    assert payload.cleaned() == {"name": "Other"}
