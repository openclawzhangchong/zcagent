import { useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Space } from "antd";
import { Palette } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { brandingApi, type Branding } from "../../../api/modules/branding";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "./TabPanelHeader";
import tabStyles from "./tabContent.module.less";

/** Matches the backend guard in api/routers/branding.py. */
const MAX_LOGO_CHARS = 300_000;

const labelStyle = { display: "block", fontWeight: 500, marginBottom: 6 } as const;

export default function BrandingSettingsPanel() {
  const { t } = useTranslation();
  const [value, setValue] = useState<Branding>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const patch = (next: Partial<Branding>) => setValue((prev) => ({ ...prev, ...next }));

  useEffect(() => {
    brandingApi
      .get()
      .then(setValue)
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);

  const save = async (payload: Branding) => {
    setSaving(true);
    try {
      setValue(await brandingApi.save(payload));
      message.success(t("advancedSettings.branding.saved"));
      // The runtime brand is read once before the first render, so a reload is
      // what actually applies the change.
      window.setTimeout(() => window.location.reload(), 800);
    } catch (err) {
      message.error(apiErrorMessage(err, t("advancedSettings.branding.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const pickLogo = (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      message.error(t("advancedSettings.branding.logoBadType"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result ?? "");
      if (url.length > MAX_LOGO_CHARS) {
        message.error(t("advancedSettings.branding.logoTooLarge"));
        return;
      }
      patch({ logo_url: url });
    };
    reader.readAsDataURL(file);
  };

  if (loading) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <TabPanelHeader
        icon={<Palette size={20} />}
        title={t("advancedSettings.branding.title")}
        description={t("advancedSettings.branding.description")}
      />
      {loadError ? (
        <Alert type="warning" showIcon message={t("advancedSettings.branding.loadFailed")} />
      ) : null}

      <div>
        <div style={labelStyle}>{t("advancedSettings.branding.nameEn")}</div>
        <Input
          value={value.name ?? ""}
          placeholder={t("advancedSettings.branding.namePlaceholder")}
          onChange={(e) => patch({ name: e.target.value || null })}
        />
      </div>
      <div>
        <div style={labelStyle}>{t("advancedSettings.branding.nameZh")}</div>
        <Input
          value={value.name_zh ?? ""}
          placeholder={t("advancedSettings.branding.namePlaceholder")}
          onChange={(e) => patch({ name_zh: e.target.value || null })}
        />
      </div>
      <div>
        <div style={labelStyle}>{t("advancedSettings.branding.tagline")}</div>
        <Input
          value={value.tagline ?? ""}
          onChange={(e) => patch({ tagline: e.target.value || null })}
        />
      </div>
      <div>
        <div style={labelStyle}>{t("advancedSettings.branding.color")}</div>
        <Space>
          <input
            type="color"
            value={/^#[0-9a-fA-F]{6}$/.test(value.color ?? "") ? value.color! : "#3d5a80"}
            onChange={(e) => patch({ color: e.target.value })}
          />
          <Input
            style={{ width: 160 }}
            value={value.color ?? ""}
            placeholder="#3D5A80"
            onChange={(e) => patch({ color: e.target.value || null })}
          />
        </Space>
      </div>
      <div>
        <div style={labelStyle}>{t("advancedSettings.branding.logo")}</div>
        <Space align="start" style={{ width: "100%" }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <Input
              value={value.logo_url ?? ""}
              placeholder={t("advancedSettings.branding.logoPlaceholder")}
              onChange={(e) => patch({ logo_url: e.target.value || null })}
            />
            <Space style={{ marginTop: 8 }}>
              <Button onClick={() => fileRef.current?.click()}>
                {t("advancedSettings.branding.logoUpload")}
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={(e) => pickLogo(e.target.files?.[0])}
              />
            </Space>
            <div className={tabStyles.sectionDesc}>
              {t("advancedSettings.branding.logoHint")}
            </div>
          </div>
          {value.logo_url ? (
            <img
              src={value.logo_url}
              alt=""
              style={{ height: 48, maxWidth: 200, objectFit: "contain" }}
            />
          ) : null}
        </Space>
      </div>

      <Space>
        <Button type="primary" loading={saving} onClick={() => save(value)}>
          {t("advancedSettings.branding.save")}
        </Button>
        <Button loading={saving} onClick={() => save({})}>
          {t("advancedSettings.branding.reset")}
        </Button>
      </Space>
    </Space>
  );
}
