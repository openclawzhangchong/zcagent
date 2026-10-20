import { useEffect, useState } from "react";
import { Alert } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { tunnelApi } from "../api/modules/tunnel";

const POLL_MS = 30_000;

/**
 * A standing reminder that this instance is reachable from the internet.
 *
 * Deliberately not confined to the settings page: the worst outcome for this
 * feature is an operator who turned it on, forgot, and believes the machine is
 * still private. Anything that fails to answer (a non-admin hitting 403, the
 * server mid-restart) is treated as "off" rather than surfacing an error --
 * this banner must never become the thing that breaks a page.
 */
export default function TunnelActiveBanner() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState("off");

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await tunnelApi.status();
        if (cancelled) return;
        setVisible(Boolean(next.state.enabled));
        setStatus(next.state.status);
      } catch {
        if (!cancelled) setVisible(false);
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (!visible) return null;

  const unverified = status !== "live";
  return (
    <Alert
      type={unverified ? "warning" : "info"}
      banner
      showIcon
      closable={false}
      data-testid="tunnel-banner"
      message={
        <span>
          {t(unverified ? "network.bannerUnverified" : "network.bannerOn")}
          <a
            style={{ marginLeft: 8 }}
            onClick={() => navigate("/admin/network")}
            data-testid="tunnel-banner-link"
          >
            {t("network.bannerManage")}
          </a>
        </span>
      }
    />
  );
}
