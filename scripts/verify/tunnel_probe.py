"""End-to-end proof for public access: open a tunnel, use it, and check what it blocks.

Reading the source cannot answer the three questions that matter here, so this
script asks the running product instead:

1. Does a tunnel actually come up and *stay* verifiable, or does "started" just
   mean a child process exists? (It fetches ``/api/health`` through the public
   URL, the same way a colleague's browser would.)
2. Does public-safe mode really deny the host-controlling surfaces over the
   tunnel while leaving local use untouched?
3. Is the "did this come through the tunnel?" decision fail-closed -- i.e. does
   a *local* request that spoofs ``Cf-Connecting-Ip`` lose access rather than
   gain it?

Boots its own scratch control plane (own ``OCTOP_HOME``, spare port) so it can
never touch a server someone is using.

    python scripts/verify/tunnel_probe.py --python .venv/Scripts/python.exe

Pass ``--keep`` to leave the tunnel up for manual poking; it is torn down on exit
otherwise, because leaving a public URL attached to a dev box is the exact thing
this feature is supposed to make visible.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "verify"))

import layout_probe as lp  # noqa: E402

BINARY_CACHE = ROOT / ".zc-verify" / "cloudflared-cache"


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def http(
    url: str,
    *,
    method: str = "GET",
    body: Any = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, str]:
    """Return ``(status, body)`` -- and never raise on a 4xx/5xx.

    The assertions here are *about* status codes, so a helper that throws on 403
    would hide exactly the result we are testing for.
    """
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")[:300]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def seed_binary(home: Path) -> None:
    """Reuse an already-verified cloudflared instead of re-pulling 53 MB.

    The download path itself is covered by ``tests/unit/infra/tunnel``; here we
    are testing the tunnel, not the network.
    """
    src = BINARY_CACHE / "cloudflared-windows-amd64.exe"
    if not src.exists():
        import platform

        name = (
            "cloudflared-windows-amd64.exe"
            if platform.system().lower() == "windows"
            else "cloudflared-linux-amd64"
        )
        src = BINARY_CACHE / name
    if not src.exists():
        print(f"  no cached cloudflared under {BINARY_CACHE}; letting the product download it")
        return
    from octop.infra.tunnel import binary as tb

    dest = home / "tunnel" / "bin" / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    tb._marker_path(dest).write_text(tb.sha256_of(dest), encoding="utf-8")
    print(f"  seeded {dest.name} ({dest.stat().st_size:,} B)")


def http_public(
    url: str, *, token: str | None = None, attempts: int = 8, **kw: Any
) -> tuple[int, str]:
    """Retry a request to a freshly minted tunnel address.

    Cloudflare needs a few seconds after cloudflared prints the URL before the
    edge route resolves; a single attempt reports 0 (DNS failure) for a tunnel
    that is about to work fine.
    """
    code, body = 0, ""
    for _ in range(attempts):
        code, body = http(url, token=token, **kw)
        if code:
            return code, body
        time.sleep(3)
    return code, body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--port", type=int, default=8096)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / ".zc-verify" / "tunnel")
    args = ap.parse_args()

    if not port_is_free(args.port):
        raise SystemExit(f"port {args.port} busy -- pass a spare --port")
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    home = out / "home"
    home.mkdir(parents=True)
    base = f"http://127.0.0.1:{args.port}"
    report: dict[str, Any] = {"base": base}

    os.environ.pop("OCTOP_HOME", None)
    sys.path.insert(0, str(ROOT / "src"))
    seed_binary(home)

    print("[1/6] boot scratch control plane", flush=True)
    proc = lp.boot(args.python, home, args.port)
    tunnel_url = ""
    try:
        print("[2/6] walk the wizard", flush=True)
        password = "Tunnel!" + os.urandom(4).hex()
        token = lp.run_setup(base, password, with_model=False)
        report["password_len"] = len(password)

        print("[3/6] preflight", flush=True)
        code, body = http(f"{base}/api/admin/tunnel/preflight", token=token)
        pre = json.loads(body) if code == 200 else {}
        report["preflight"] = pre
        print(f"  HTTP {code} ready={pre.get('ready')}", flush=True)
        for item in pre.get("items", []):
            print(f"    {'ok ' if item['ok'] else 'BAD'} {item['key']}", flush=True)

        print("[4/6] open the tunnel", flush=True)
        code, body = http(
            f"{base}/api/admin/tunnel",
            method="POST",
            body={"password": password, "safe_mode": True, "consent_ack": True},
            token=token,
        )
        print(f"  POST /api/admin/tunnel -> HTTP {code}", flush=True)
        if code != 200:
            report["start_error"] = body[:300]
            raise SystemExit(f"could not open the tunnel: {body[:300]}")

        deadline = time.time() + 240
        state: dict[str, Any] = {}
        while time.time() < deadline:
            code, body = http(f"{base}/api/admin/tunnel", token=token)
            state = json.loads(body).get("state", {})
            if state.get("status") not in ("starting", "connecting"):
                break
            time.sleep(3)
        tunnel_url = str(state.get("url") or "")
        report["state"] = state
        print(f"  status={state.get('status')} url={tunnel_url or '(none)'}", flush=True)
        if state.get("last_error"):
            print(f"  last_error={state['last_error']}", flush=True)

        checks: dict[str, bool] = {}

        print("[5/6] use it from outside, and check what is blocked", flush=True)
        if tunnel_url:
            code, body = http_public(f"{tunnel_url}/api/health", timeout=40)
            print(f"  GET {tunnel_url}/api/health -> {code}", flush=True)
            if code != 200:
                # The first automatic probe races DNS propagation. Ask the
                # product to re-check the way the UI's "重新验证" button does,
                # and assert that path converges -- an unverified status that
                # can never become verified is a dead end for the user.
                for attempt in range(3):
                    code_r, body_r = http(
                        f"{base}/api/admin/tunnel/probe",
                        method="POST",
                        token=token,
                        timeout=180,
                    )
                    rep = json.loads(body_r) if code_r == 200 else {}
                    ok_rep = rep.get("result", {}).get("ok")
                    print(
                        f"  POST /probe #{attempt + 1} -> {code_r} ok={ok_rep}",
                        flush=True,
                    )
                    if ok_rep:
                        break
                    time.sleep(10)
                code, body = http_public(f"{tunnel_url}/api/health", attempts=4, timeout=40)
                print(f"  GET /api/health after re-check -> {code}", flush=True)
            checks["public health answers"] = code == 200 and '"ok"' in body
            _, body_s = http(f"{base}/api/admin/tunnel", token=token)
            checks["product reports live after re-check"] = (
                json.loads(body_s).get("state", {}).get("status") == "live"
            )

            for path, label in (
                ("/api/filesystem/dirs?path=.", "filesystem browsing"),
                ("/api/browser/env-status", "browser control"),
                ("/api/desktop/status", "remote desktop"),
            ):
                code_t, _ = http_public(tunnel_url + path, token=token, timeout=40)
                code_l, _ = http(base + path, token=token)
                checks[f"{label} blocked over tunnel"] = code_t == 403
                checks[f"{label} still allowed locally"] = code_l != 403
                print(f"  {label:22s} tunnel={code_t} local={code_l}", flush=True)

            # Fail-closed direction: a local request that *claims* to be from the
            # tunnel must lose access, never gain it.
            code_s, _ = http(
                f"{base}/api/filesystem/dirs?path=.",
                token=token,
                headers={"Cf-Connecting-Ip": "8.8.8.8"},
            )
            checks["spoofed marker fails closed"] = code_s == 403
            print(f"  local request spoofing the marker -> {code_s}", flush=True)

            code_c, _ = http_public(f"{tunnel_url}/api/agents", token=token, timeout=40)
            checks["chat data still reachable over tunnel"] = code_c == 200
            print(f"  GET /api/agents over tunnel -> {code_c}", flush=True)
        else:
            checks["tunnel came up"] = False

        print("[6/6] close it", flush=True)
        code, _ = http(f"{base}/api/admin/tunnel", method="DELETE", token=token)
        checks["stop accepted"] = code == 200
        time.sleep(3)
        _, body = http(f"{base}/api/admin/tunnel", token=token)
        final = json.loads(body).get("state", {})
        checks["state cleared after stop"] = final.get("status") == "off" and not final.get("url")
        print(f"  DELETE -> {code}; final status={final.get('status')}", flush=True)
        if tunnel_url and not args.keep:
            code_after, _ = http(tunnel_url + "/api/health", timeout=25)
            checks["public address stops answering after stop"] = code_after in (
                0,
                530,
                404,
                502,
                503,
            )
            print(f"  {tunnel_url}/api/health after stop -> {code_after}", flush=True)

        report["checks"] = checks
        report["tunnel_url_seen"] = bool(tunnel_url)
        ok = all(checks.values())
        report["verdict"] = "OK" if ok else "FAIL"
        print("", flush=True)
        for name, passed in checks.items():
            print(f"  {'PASS' if passed else 'FAIL'}  {name}", flush=True)
        print(f"\nverdict: {report['verdict']}", flush=True)
        return 0 if ok else 1
    finally:
        if args.keep and tunnel_url:
            print(f"leaving the tunnel up: {tunnel_url}", flush=True)
        else:
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=20)
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
