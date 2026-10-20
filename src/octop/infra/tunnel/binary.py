"""Where cloudflared comes from, and how we know it is the real thing.

The binary is **not** shipped inside the installer: it is 52.8 MB against a
233 MB package for a feature most installs never turn on, so it is fetched the
first time someone actually decides to expose the server, and every download is
SHA-256 checked against the digest published by the upstream release.

Version is pinned rather than "latest" for two reasons that both bit us with the
bundled Node runtime: an unpinned third-party binary makes a reproducible build
impossible, and cloudflared self-updates by default (it restarts itself with a
newer build) which would silently replace what we verified. We therefore pass
``--no-autoupdate`` everywhere and control upgrades from ``CLOUDFLARED_VERSION``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from octop.infra.utils.paths import PathLayout

log = logging.getLogger(__name__)

CLOUDFLARED_VERSION = "2026.10.1"

_RELEASE_BASE = f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}"


@dataclass(frozen=True)
class Artifact:
    filename: str
    sha256: str
    bytes: int

    @property
    def url(self) -> str:
        return f"{_RELEASE_BASE}/{self.filename}"


# Digests read from the upstream GitHub Release API (``assets[].digest``), not
# guessed. ``scripts/verify/tunnel_probe.py`` re-checks them against the release
# so a stale pin fails loudly instead of downloading the wrong bytes forever.
_PLATFORM_ARTIFACTS: dict[str, Artifact] = {
    "windows-amd64": Artifact(
        "cloudflared-windows-amd64.exe",
        "4d2490e74082c5d48dbfedaf92576fa5bd1702379ab88eb7faa0cfbe8dc891b6",
        55_325_120,
    ),
    "linux-amd64": Artifact(
        "cloudflared-linux-amd64",
        "3bfc539f45d2620c71debb7a86be0efa737ed5ccbad9eb85c787116900e5c586",
        40_227_032,
    ),
    "linux-arm64": Artifact(
        "cloudflared-linux-arm64",
        # Not yet measured on real hardware; see tunnel_probe.py's platform list.
        "",
        0,
    ),
}

# Apache-2.0 requires the notice to travel with the binary.
LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
NOTICE = (
    "This product bundles cloudflared (https://github.com/cloudflare/cloudflared),\n"
    "copyright Cloudflare, Inc., licensed under the Apache License 2.0.\n"
    f"Pinned version: {CLOUDFLARED_VERSION}.\n"
)


def platform_key() -> str:
    """Map the running OS/arch onto ``_PLATFORM_ARTIFACTS`` keys."""
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine, machine
    )
    if system == "windows":
        return f"windows-{arch}"
    if system == "darwin":
        return f"darwin-{arch}"
    return f"{system}-{arch}"


def artifact_for(key: str | None = None) -> Artifact | None:
    """The pinned artifact for *key*, or ``None`` when we have no digest for it.

    A missing digest is not an error here: the caller turns it into "this
    platform is not supported for public access" rather than downloading
    something we cannot verify.
    """
    art = _PLATFORM_ARTIFACTS.get(key or platform_key())
    if art is None or not art.sha256:
        return None
    return art


def tunnel_dir() -> Path:
    return PathLayout.from_env().root / "tunnel"


def binary_path(key: str | None = None) -> Path:
    art = artifact_for(key)
    name = art.filename if art else "cloudflared-unsupported"
    return tunnel_dir() / "bin" / name


def _marker_path(dest: Path) -> Path:
    """Sidecar holding the digest we verified. ``with_suffix`` cannot express
    ``.exe.verified``, hence the plain name concat."""
    return dest.parent / (dest.name + ".verified")


def is_ready(key: str | None = None) -> bool:
    """True when a verified binary for this platform is already on disk."""
    art = artifact_for(key)
    if art is None:
        return False
    dest = binary_path(key)
    marker = _marker_path(dest)
    return (
        dest.exists()
        and marker.exists()
        and marker.read_text(encoding="utf-8").strip() == art.sha256
    )


def ensure_binary(timeout: int = 300) -> Path:
    """Return a verified cloudflared for this platform, downloading it if needed.

    Raises ``RuntimeError`` with a user-presentable message: this runs when a
    human clicks "开启公网访问", and the failure is usually "your network cannot
    reach github.com", which must not look like a bug in us.
    """
    key = platform_key()
    art = artifact_for(key)
    if art is None:
        raise RuntimeError(f"公网访问暂不支持当前平台：{key}")

    dest = binary_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    marker = _marker_path(dest)

    if is_ready(key):
        return dest

    tmp = dest.parent / (dest.name + ".download")
    try:
        _download(art.url, tmp, art.bytes, timeout)
        digest = sha256_of(tmp)
        if digest != art.sha256:
            raise RuntimeError(
                "cloudflared 校验失败：下载到的不是发布页声明的那份"
                f"（期望 {art.sha256[:12]}…，实际 {digest[:12]}…）"
            )
        if os.name != "posix":
            dest.unlink(missing_ok=True)
        shutil.move(str(tmp), str(dest))
        if os.name == "posix":
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        marker.write_text(art.sha256, encoding="utf-8")
        (tunnel_dir() / "LICENSE.cloudflared.txt").write_text(NOTICE, encoding="utf-8")
    except RuntimeError:
        raise
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"下载 cloudflared 失败：{exc.reason}。公网访问组件需要能访问 github.com；"
            "内网机器可以先在能出网的机器上把它放到 "
            f"{dest}"
        ) from exc
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def _download(url: str, dest: Path, expect_bytes: int, timeout: int) -> None:
    """Stream to *dest*, then trust only the byte count -- never the exit code."""
    req = urllib.request.Request(url, headers={"User-Agent": "zcagent-tunnel"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    got = dest.stat().st_size
    if expect_bytes and got != expect_bytes:
        raise RuntimeError(f"下载不完整：{got} / {expect_bytes} 字节")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()
