"""Cloudflare Tunnel lifecycle: start, prove it works, keep it alive, stop.

Two rules shape this module, and both come from defects we have already been
burned by elsewhere in the product:

* **A live subprocess is not evidence of a working tunnel.** The plan's whole
  value is "someone outside can open this URL", so starting is not done until
  we have fetched ``/api/health`` *through the public address* and got a 200.
  Everything short of that is reported as ``connecting``/``unverified``, never
  as a green "已开启".
* **Never restart into a silent loop.** A tunnel that dies and comes back with
  a different random address is worse than one that stays visibly dead, because
  colleagues' bookmarks quietly rot. Repeated failures therefore end in
  ``degraded`` with the last error surfaced in the UI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from octop.infra.tunnel import binary

log = logging.getLogger(__name__)

SETTINGS_KEY = "cloudflare_tunnel"

# Only addresses from the quick-tunnel namespace may ever be probed. This is the
# allowlist *and* the SSRF guard: the string comes from a child process' stderr,
# so we must not hand it to urllib as-is.
_QUICK_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# After this many seconds without a URL from cloudflared, give up. The edge
# handshake is normally ~2 s; a minute means the network cannot reach it.
_URL_TIMEOUT_S = 60.0
_PROBE_TIMEOUT_S = 20.0
# The address is minted a moment before the edge route and the local resolver
# catch up, and on this network that gap measured ~40 s. The probe runs in a
# background task, so a generous budget costs nobody anything -- whereas a short
# one reports a working tunnel as "unverified" and leaves the user staring at a
# warning that was never true.
_PROBE_ATTEMPTS = 12
_PROBE_DELAY_S = 5.0

# Escalating waits between restarts; running out marks the tunnel degraded.
_BACKOFF_S: tuple[int, ...] = (5, 30, 120, 300)

_TERMINATE_GRACE_S = 5.0


@dataclass
class TunnelState:
    """What the UI shows. Persisted as JSON in the ``settings`` KV."""

    enabled: bool = False
    status: str = "off"  # off | starting | live | connecting | degraded | error
    mode: str = "quick"
    url: str = ""
    pid: int | None = None
    started_at: float | None = None
    verified_at: float | None = None
    last_error: str = ""
    failures: int = 0
    # G5: strip the host-controlling surfaces from anything arriving over the
    # tunnel. Default-on; turning it off is an explicit, per-install decision.
    safe_mode: bool = True
    # G6: the operator acknowledged that traffic transits a third-party edge.
    consent_ack: bool = False
    binary_version: str = binary.CLOUDFLARED_VERSION
    updated_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        """The shape the dashboard reads -- no paths, no PIDs beyond status."""
        data = asdict(self)
        data.pop("consent_ack", None)
        data["since"] = self.started_at
        return data


class TunnelManager:
    """One quick tunnel per server process; mirrors ``terminal.py``'s registry shape."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._watch: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._state = TunnelState()
        self._services: Any = None
        self._port = 8088
        self._stopping = False
        self._bound = False

    # ── persistence ────────────────────────────────────────────────────────

    def bind(self, services: Any, port: int) -> None:
        """Wire in ``server.services`` once the app is assembled.

        Idempotent, and it has to be: every request handler calls it, and
        re-running the load would read this tunnel's own ``enabled: true`` back
        off disk and classify the live process as leftover-from-a-restart --
        which is exactly how the first status poll used to kill the tunnel.
        """
        if self._bound:
            return
        self._bound = True
        self._services = services
        self._port = port
        self._load()

    def _load(self) -> None:
        raw = self._persist_get()
        if not raw:
            return
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("tunnel: dropping unreadable persisted state")
            return
        known = {f.name for f in fields(TunnelState)}
        self._state = TunnelState(**{k: v for k, v in blob.items() if k in known})
        # A PID we did not spawn in this process is worthless: the server may
        # have restarted and that pid now belongs to something else.
        self._state.pid = None
        # Do **not** auto-resume. A quick tunnel gets a new random address every
        # time, so silently restarting one invalidates every link colleagues
        # saved -- the failure mode this feature must not have. Named tunnels
        # (fixed hostname) are the ones that can come back on boot.
        if self._state.enabled:
            self._state.enabled = False
            self._state.status = "stopped"
            self._state.url = ""
            self._state.last_error = (
                "服务重启后隧道不会自动恢复：试用地址每次都会变，"
                "自动重连只会让你发给同事的链接悄悄失效。需要公网访问请重新开启，"
                "长期使用请改用固定域名的正式隧道。"
            )
            self._persist()

    def _persist_get(self) -> str | None:
        if self._services is None:
            return None
        try:
            return str(self._services.settings_repo.get(SETTINGS_KEY) or "") or None
        except Exception as exc:  # noqa: BLE001 - never let state load break boot
            log.warning("tunnel: settings read failed: %s", exc)
            return None

    def _persist(self) -> None:
        if self._services is None:
            return
        self._state.updated_at = time.time()
        try:
            self._services.settings_repo.set(SETTINGS_KEY, json.dumps(asdict(self._state)))
        except Exception as exc:  # noqa: BLE001
            log.warning("tunnel: settings write failed: %s", exc)

    # ── surface ────────────────────────────────────────────────────────────

    @property
    def state(self) -> TunnelState:
        return self._state

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def start(self, *, safe_mode: bool = True, consent_ack: bool = False) -> TunnelState:
        """Open the tunnel. Idempotent: a second call while live is a no-op."""
        async with self._lock:
            if self.running:
                return self._state
            self._stopping = False
            self._state.enabled = True
            self._state.safe_mode = safe_mode
            self._state.consent_ack = consent_ack
            self._state.status = "starting"
            self._state.last_error = ""
            self._state.failures = 0
            self._state.started_at = time.time()
            self._state.verified_at = None
            self._state.url = ""
            self._persist()

        try:
            path = await asyncio.get_running_loop().run_in_executor(None, binary.ensure_binary)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI verbatim
            await self._fail(str(exc), permanent=True)
            return self._state

        await self._spawn(path)
        return self._state

    async def _spawn(self, path: Path) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                str(path),
                "tunnel",
                "--url",
                f"http://127.0.0.1:{self._port}",
                "--no-autoupdate",
                # debug logs every request header, which would put bearer tokens
                # into ~/.octop/octop.log.
                "--loglevel",
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as exc:
            await self._fail(f"无法启动 cloudflared：{exc}", permanent=True)
            return

        self._state.pid = self._proc.pid
        self._persist()
        self._watch = asyncio.create_task(self._watchdog())

    async def _watchdog(self) -> None:
        """Follow the child: learn its address, then keep it alive or give up."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        url = ""
        while True:
            try:
                # The deadline only guards "we never saw an address at all".
                # Once connected, a quiet tunnel produces no output for minutes
                # and that is normal, not a failure.
                line = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=None if url else _URL_TIMEOUT_S,
                )
            except TimeoutError:
                await self._fail(
                    "60 秒内没有拿到公网地址。常见原因是这台机器连不上 "
                    "argotunnel.com / trycloudflare.com。"
                )
                break
            if not line:
                break  # EOF: the process is exiting
            text = line.decode("utf-8", "replace")
            if url:
                log.debug("cloudflared: %s", text.rstrip())
                continue
            found = _QUICK_URL_RE.search(text)
            if found:
                url = found.group(0)
                self._state.url = url
                self._state.status = "connecting"
                async with self._lock:
                    self._persist()
                asyncio.create_task(self._verify(url))
        await self._on_exit(proc)

    async def _verify(self, url: str) -> None:
        """Prove the public path works, not merely that the child is alive."""
        ok, detail = await asyncio.get_running_loop().run_in_executor(None, self._probe, url)
        async with self._lock:
            if self._state.url != url:
                return  # superseded by a restart
            if ok:
                self._state.status = "live"
                self._state.verified_at = time.time()
                self._state.last_error = ""
            else:
                self._state.status = "unverified"
                self._state.last_error = detail
            self._persist()
        if self._services is not None:
            with contextlib.suppress(Exception):
                self._services.audit_repo.system_event(
                    "tunnel.verified" if ok else "tunnel.verify_failed",
                    target=url,
                    payload=detail if not ok else None,
                )

    @staticmethod
    def _probe(url: str) -> tuple[bool, str]:
        import urllib.error
        import urllib.request

        target = f"{url.rstrip('/')}/api/health"
        last = ""
        for attempt in range(_PROBE_ATTEMPTS):
            try:
                with urllib.request.urlopen(target, timeout=_PROBE_TIMEOUT_S) as resp:
                    body = resp.read(256).decode("utf-8", "replace")
                    if resp.status == 200 and '"ok"' in body:
                        return True, ""
                    last = f"HTTP {resp.status}"
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
            except Exception as exc:  # noqa: BLE001
                last = f"{type(exc).__name__}: {exc}"
            if attempt < _PROBE_ATTEMPTS - 1:
                time.sleep(_PROBE_DELAY_S)
        return False, (
            f"隧道已建立，但连续 {_PROBE_ATTEMPTS} 次公网探活都没通过（{last}）。"
            "可能是地址刚生成、Cloudflare 边缘还没生效，稍等几秒刷新看看；"
            "也可能是这台机器到 Cloudflare 边缘的链路不通——国内可达性不稳定，是已知限制。"
        )

    async def reverify(self) -> dict[str, Any]:
        """Run the public check again, on demand.

        The first probe races Cloudflare's own propagation and the local
        resolver's negative cache, so ``unverified`` is common seconds after a
        tunnel comes up and means nothing on its own. Without a way to re-ask,
        the UI would be stuck showing a warning about a tunnel that works fine.
        """
        url = self._state.url
        if not url:
            return {"ok": False, "detail": "隧道没有地址，先关闭再重新开启。"}
        ok, detail = await asyncio.get_running_loop().run_in_executor(None, self._probe, url)
        async with self._lock:
            if ok:
                self._state.status = "live"
                self._state.verified_at = time.time()
                self._state.last_error = ""
            else:
                self._state.status = "unverified"
                self._state.last_error = detail
            self._persist()
        return {"ok": ok, "detail": detail}

    async def _on_exit(self, proc: asyncio.subprocess.Process) -> None:
        code = await proc.wait()
        async with self._lock:
            if self._stopping:
                self._state.status = "off"
                self._state.url = ""
                self._state.pid = None
                self._persist()
                return
        delay = None
        if self._state.enabled:
            attempt = self._state.failures
            if attempt < len(_BACKOFF_S):
                delay = _BACKOFF_S[attempt]
                async with self._lock:
                    self._state.failures = attempt + 1
                    self._state.status = "connecting"
                    self._state.last_error = (
                        f"隧道进程退出（code={code}），{delay} 秒后自动重试"
                        f"（第 {attempt + 1}/{len(_BACKOFF_S)} 次）"
                    )
                    self._persist()
            else:
                await self._fail(
                    f"隧道连续 {len(_BACKOFF_S)} 次启动后都退出了（code={code}），"
                    "已停止自动重试。下方是最后一条错误。"
                )
        if delay is not None:
            await asyncio.sleep(delay)
            if self._state.enabled and not self._stopping:
                path = binary.binary_path()
                if path.exists():
                    await self._spawn(path)

    async def _fail(self, message: str, *, permanent: bool = False) -> None:
        async with self._lock:
            self._state.status = "error" if permanent else "degraded"
            self._state.last_error = message
            self._state.url = ""
            if permanent:
                self._state.enabled = False
            self._persist()
        log.warning("tunnel: %s", message)

    async def stop(self) -> TunnelState:
        async with self._lock:
            self._stopping = True
            self._state.enabled = False
            self._state.status = "off"
            self._state.url = ""
            self._persist()
            proc, watch = self._proc, self._watch
        if watch is not None and watch is not asyncio.current_task():
            watch.cancel()
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE_S)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
        async with self._lock:
            self._proc = None
            self._watch = None
            self._state.pid = None
            self._persist()
        return self._state

    async def set_safe_mode(self, enabled: bool) -> None:
        async with self._lock:
            self._state.safe_mode = enabled
            self._persist()

    async def shutdown(self) -> None:
        """Called on server exit so we never orphan a child on the customer's box."""
        await self.stop()


_manager: TunnelManager | None = None


def get_manager() -> TunnelManager:
    global _manager
    if _manager is None:
        _manager = TunnelManager()
    return _manager
