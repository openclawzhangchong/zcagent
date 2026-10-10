import { Button } from "antd";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";
import { DEFAULT_DOWNLOAD_URL, downloadUrl } from "../../../branding/runtime";
import styles from "./UpdateConfig.module.less";

/**
 * Client downloads, shown under the update page.
 *
 * The address comes from the branding layer: a stock install points at our
 * Releases page, and an intranet deployment overrides it with its own download
 * site. This card replaces upstream's "curl | bash" upgrade guide, which on this
 * product would install somebody else's build.
 */
export default function ClientDownloads() {
  const { t } = useTranslation();
  const url = downloadUrl();
  const isDefault = url === DEFAULT_DOWNLOAD_URL;

  return (
    <section
      className={styles.panel}
      aria-label={t("advancedSettings.clients.title")}
    >
      <div className={styles.panelTitleRow}>
        <span className={styles.panelTitleIcon}>
          <Download size={16} />
        </span>
        <h3 className={styles.panelTitle}>
          {t("advancedSettings.clients.title")}
        </h3>
      </div>
      <p className={styles.panelDesc}>{t("advancedSettings.clients.desc")}</p>
      <div>
        <Button type="primary" href={url} target="_blank" rel="noreferrer">
          {t("advancedSettings.clients.open")}
        </Button>
      </div>
      <p className={styles.stableOnlyHint}>
        {isDefault
          ? t("advancedSettings.clients.hintDefault")
          : t("advancedSettings.clients.hintCustom")}
      </p>
    </section>
  );
}
