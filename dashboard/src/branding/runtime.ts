/**
 * Runtime OEM branding, loaded once before React mounts.
 *
 * Build-time branding (brand/brand.yaml) decides what ships; this is the
 * per-deployment override an admin sets afterwards via PUT /api/branding.
 * Absent values fall back to the build-time brand, so a stock install is
 * unaffected.
 */

export type Branding = {
  name?: string | null;
  name_zh?: string | null;
  tagline?: string | null;
  color?: string | null;
  logo_url?: string | null;
};

let current: Branding = {};

function applyFavicon(logoUrl: string | null | undefined) {
  if (!logoUrl) return;
  for (const rel of ["icon", "apple-touch-icon"]) {
    for (const link of document.querySelectorAll(`link[rel~="${rel}"]`)) {
      link.setAttribute("href", logoUrl);
    }
  }
}

export async function loadBranding(): Promise<Branding> {
  try {
    // Plain fetch, not api/request.ts: the endpoint is auth-exempt and a 401
    // handler there would be wrong for the pre-login screen.
    const res = await fetch("/api/branding", { cache: "no-store" });
    if (res.ok) current = (await res.json()) as Branding;
  } catch {
    current = {}; // offline / server still booting -- keep the built-in brand
  }
  applyFavicon(current.logo_url);
  return current;
}

export function branding(): Branding {
  return current;
}

export function brandingName(language?: string): string | null {
  const zh = language?.toLowerCase().startsWith("zh");
  const name = zh
    ? current.name_zh ?? current.name
    : current.name ?? current.name_zh;
  return name?.trim() || null;
}
