import { request } from "../request";

/** Public access via a Cloudflare Tunnel. Admin-only endpoints. */

export interface TunnelState {
  enabled: boolean;
  /** off | starting | live | connecting | degraded | unverified | error | stopped */
  status: string;
  mode: string;
  url: string;
  pid: number | null;
  since: number | null;
  verified_at: number | null;
  last_error: string;
  failures: number;
  safe_mode: boolean;
  binary_version: string;
  updated_at: number;
}

export interface PreflightItem {
  key: string;
  label_zh: string;
  label_en: string;
  ok: boolean;
  blocking: boolean;
  fix_path: string;
  why_zh?: string;
  why_en?: string;
  value?: boolean;
}

export interface TunnelStatus {
  state: TunnelState;
  running: boolean;
  binary_ready: boolean;
  binary_version: string;
  local_port: number;
}

export const tunnelApi = {
  status: () => request<TunnelStatus>("/admin/tunnel"),
  preflight: () =>
    request<{ items: PreflightItem[]; ready: boolean }>(
      "/admin/tunnel/preflight",
    ),
  start: (password: string, safeMode: boolean, consentAck: boolean) =>
    request<{ state: TunnelState }>("/admin/tunnel", {
      method: "POST",
      body: JSON.stringify({
        password,
        safe_mode: safeMode,
        consent_ack: consentAck,
      }),
    }),
  stop: () =>
    request<{ state: TunnelState }>("/admin/tunnel", { method: "DELETE" }),
  reprobe: () =>
    request<{ result: { ok: boolean; detail: string }; state: TunnelState }>(
      "/admin/tunnel/probe",
      { method: "POST" },
    ),
  setSafeMode: (safeMode: boolean) =>
    request<{ state: TunnelState }>("/admin/tunnel", {
      method: "PATCH",
      body: JSON.stringify({ safe_mode: safeMode }),
    }),
};
