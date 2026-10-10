"""Tests for scripts/rebrand.py's text transform.

The transform is what runs over ~3,200 files during an OEM rebrand, so a single
over-eager literal is not a typo -- it silently breaks a live integration.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def rebrand():
    spec = importlib.util.spec_from_file_location("rebrand", REPO / "scripts" / "rebrand.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def brand() -> dict:
    return yaml.safe_load((REPO / "brand" / "brand.yaml").read_text(encoding="utf-8"))


def test_help_site_url_is_rewritten_but_the_channel_endpoint_survives(
    rebrand, brand: dict
) -> None:
    """`https://github.com/openclawzhangchong/zcagent` is a prefix of the upstream OctoBot endpoint.

    A plain literal swap would turn that endpoint into a dead host, so the rule
    needs its boundary -- this test is the reason.
    """
    src = (
        'const HELP = "https://github.com/openclawzhangchong/zcagent";\n'
        'const BOT = "https://octop.cloud.tencent.com";\n'
        'const deep = "https://github.com/openclawzhangchong/zcagent/docs/intro";\n'
    )
    out = rebrand.transform(src, brand, "en")
    assert "https://octop.cloud.tencent.com" in out, "third-party channel endpoint was rewritten"
    assert '"https://github.com/openclawzhangchong/zcagent";' in out
    assert "github.com/openclawzhangchong/zcagent/docs/intro" in out


def test_identifiers_the_token_rule_must_not_touch(rebrand, brand: dict) -> None:
    src = (
        'X-Octop-Agent-Id\nOctopError\noctop-harness\n$OCTOP_HOME\n'
        'prefixCls="octop"\n~/octop-login.txt\ncn.jiuyeke.zcagent\n'
    )
    out = rebrand.transform(src, brand, "en")
    for keep in ("X-Octop-Agent-Id", "OctopError", "octop-harness", "$OCTOP_HOME", "octop-login"):
        assert keep in out, f"{keep} was swept"
    assert "cn.jiuyeke.zcagent" in out  # the reverse-domain identity is swapped


def test_artifact_prefix_still_rewritten_with_the_header_boundary(rebrand, brand: dict) -> None:
    """The boundary that protects `X-Octop-*` must not also stop release names --
    NSIS names them from `productName` while the workflow globs the literal, so a
    missed rewrite fails the upload step with if-no-files-found: error."""
    src = (
        "asset: zcagent-desktop-windows-amd64-1.0.0.exe\n"
        "asset: zcagent-portable-linux-amd64-1.0.0.zip\n"
        "header: X-Octop-Access-Token\n"
    )
    out = rebrand.transform(src, brand, "en")
    assert "zcagent-desktop-windows-amd64-1.0.0.exe" in out
    assert "zcagent-portable-linux-amd64-1.0.0.zip" in out
    assert "X-Octop-Access-Token" in out


def test_zh_locale_uses_the_chinese_name_and_en_uses_the_latin_one(rebrand, brand: dict) -> None:
    assert rebrand.transform("欢迎使用 Octop", brand, "zh") == "欢迎使用 智策"
    assert rebrand.transform("Welcome to Octop", brand, "en") == "Welcome to zcagent"


def test_pattern_literals_are_optional(rebrand) -> None:
    """A literal without `pattern` still needs `from` -- guard the KeyError that
    adding the pattern branch nearly introduced."""
    with pytest.raises(KeyError):
        rebrand.transform("x", {"identity": {"literals": [{"to": "y"}]}, "name": {"en": "z"}}, "en")
