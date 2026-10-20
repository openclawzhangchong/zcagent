import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  Modal,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";
import {
  Copy,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import PageShell from "../../../layouts/PageShell";
import { apiErrorMessage } from "../../../utils/apiError";
import { copyText } from "../../../utils/copyText";
import {
  tunnelApi,
  type PreflightItem,
  type TunnelStatus,
} from "../../../api/modules/tunnel";
import styles from "./index.module.less";

const { Text, Paragraph } = Typography;

/** While the tunnel is in one of these, the UI has to keep asking. */
const TRANSIENT = new Set(["starting", "connecting"]);
const POLL_MS = 3000;

function statusColor(status: string): string {
  if (status === "live") return "green";
  if (status === "unverified" || status === "degraded") return "orange";
  if (status === "error") return "red";
  if (TRANSIENT.has(status)) return "blue";
  return "default";
}

export default function NetworkPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [status, setStatus] = useState<TunnelStatus | null>(null);
  const [items, setItems] = useState<PreflightItem[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [safeMode, setSafeMode] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [password, setPassword] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const state = status?.state;
  const active = Boolean(state?.enabled);

  const refresh = useCallback(async () => {
    try {
      const [next, pre] = await Promise.all([
        tunnelApi.status(),
        tunnelApi.preflight(),
      ]);
      setStatus(next);
      setItems(pre.items);
      setReady(pre.ready);
      setSafeMode(next.state.safe_mode);
      return next;
    } catch (err) {
      message.error(apiErrorMessage(err, t("network.actionFailed"), t));
      return null;
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll only while something is actually in flight, then stop: an idle page
  // should not keep hitting the server every few seconds.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (state && TRANSIENT.has(state.status)) {
      timer.current = setTimeout(() => void refresh(), POLL_MS);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [state?.status, refresh, state]);

  const label = (item: PreflightItem) =>
    i18n.language === "zh" ? item.label_zh : item.label_en;
  const why = (item: PreflightItem) =>
    i18n.language === "zh" ? item.why_zh : item.why_en;

  const handleStart = async () => {
    if (!password) {
      message.warning(t("network.needPassword"));
      return;
    }
    setBusy(true);
    try {
      await tunnelApi.start(password, safeMode, consent);
      setDialogOpen(false);
      setPassword("");
      message.info(t("network.starting"));
      await refresh();
    } catch (err) {
      message.error(apiErrorMessage(err, t("network.actionFailed"), t));
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    try {
      await tunnelApi.stop();
      await refresh();
    } catch (err) {
      message.error(apiErrorMessage(err, t("network.actionFailed"), t));
    } finally {
      setBusy(false);
    }
  };

  const handleSafeMode = async (on: boolean) => {
    setSafeMode(on);
    try {
      await tunnelApi.setSafeMode(on);
      await refresh();
    } catch (err) {
      setSafeMode(!on);
      message.error(apiErrorMessage(err, t("network.actionFailed"), t));
    }
  };

  const handleReprobe = async () => {
    setBusy(true);
    try {
      const next = await tunnelApi.reprobe();
      setStatus((prev) => (prev ? { ...prev, state: next.state } : prev));
      if (next.result.ok) message.success(t("network.reprobeOk"));
      else message.warning(t("network.reprobeFailed"));
    } catch (err) {
      message.error(apiErrorMessage(err, t("network.actionFailed"), t));
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    if (!state?.url) return;
    const ok = await copyText(state.url);
    if (ok) message.success(t("network.copied"));
    else message.warning(t("network.copyFailed"));
  };

  return (
    <PageShell
      title={t("pageShell.network.title")}
      subtitle={t("pageShell.network.subtitle")}
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Card
          title={
            <Space>
              <span>{t("network.switchTitle")}</span>
              <Tag color={statusColor(state?.status || "off")}>
                {t(`network.status.${state?.status || "off"}`)}
              </Tag>
            </Space>
          }
          extra={
            <Switch
              checked={active}
              loading={busy}
              disabled={!active && !ready}
              onChange={(on) => (on ? setDialogOpen(true) : void handleStop())}
              data-testid="tunnel-switch"
            />
          }
        >
          <Paragraph type="secondary" style={{ marginBottom: 12 }}>
            {t("network.switchHelp")}
          </Paragraph>

          {state?.last_error ? (
            <Alert
              type={state.status === "live" ? "info" : "warning"}
              showIcon
              message={state.last_error}
              style={{ marginBottom: 12 }}
            />
          ) : null}

          {active && state?.url ? (
            <div className={styles.addressRow}>
              <Input
                readOnly
                value={state.url}
                className={styles.addressInput}
              />
              <Button
                icon={<Copy size={14} />}
                onClick={() => void handleCopy()}
              >
                {t("network.copy")}
              </Button>
              <Button
                icon={<ExternalLink size={14} />}
                href={state.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("network.open")}
              </Button>
              <Button
                icon={<RefreshCw size={14} />}
                onClick={() => void refresh()}
              >
                {t("network.refresh")}
              </Button>
              {state.status === "unverified" ? (
                <Button
                  icon={<ShieldCheck size={14} />}
                  loading={busy}
                  onClick={() => void handleReprobe()}
                  data-testid="tunnel-reprobe"
                >
                  {t("network.reprobe")}
                </Button>
              ) : null}
            </div>
          ) : null}

          {active && state?.url ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
              message={t("network.ephemeralTitle")}
              description={t("network.ephemeralBody")}
            />
          ) : null}

          <div className={styles.safeModeRow}>
            <Space>
              {safeMode ? (
                <ShieldCheck size={16} className={styles.safeIcon} />
              ) : (
                <ShieldAlert size={16} className={styles.unsafeIcon} />
              )}
              <Text>{t("network.safeModeTitle")}</Text>
            </Space>
            <Switch
              checked={safeMode}
              onChange={(on) => void handleSafeMode(on)}
              data-testid="tunnel-safe-mode"
            />
          </div>
          <Paragraph type="secondary" style={{ marginTop: 6, marginBottom: 0 }}>
            {t("network.safeModeBody")}
          </Paragraph>
        </Card>

        {!active ? (
          <Card title={t("network.preflightTitle")}>
            {items.map((item) => (
              <div className={styles.checkRow} key={item.key}>
                <span
                  className={
                    item.ok
                      ? styles.checkOk
                      : item.blocking
                      ? styles.checkBad
                      : styles.checkInfo
                  }
                >
                  {item.ok ? "✓" : item.blocking ? "✗" : "•"}
                </span>
                <div className={styles.checkBody}>
                  <Text>{label(item)}</Text>
                  {why(item) ? (
                    <div className={styles.checkWhy}>
                      <Text type="secondary">{why(item)}</Text>
                    </div>
                  ) : null}
                </div>
                {item.fix_path && !item.ok ? (
                  <Button size="small" onClick={() => navigate(item.fix_path)}>
                    {t("network.goFix")}
                  </Button>
                ) : null}
              </div>
            ))}
            <Checkbox
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className={styles.consent}
            >
              {t("network.consent")}
            </Checkbox>
            <div className={styles.consentHelp}>
              <Text type="secondary">{t("network.consentHelp")}</Text>
            </div>
          </Card>
        ) : null}
      </Space>

      <Modal
        open={dialogOpen}
        title={t("network.confirmTitle")}
        okText={t("network.confirmOk")}
        cancelText={t("common.cancel")}
        confirmLoading={busy}
        okButtonProps={{ disabled: !consent, danger: !safeMode }}
        onOk={() => void handleStart()}
        onCancel={() => setDialogOpen(false)}
        destroyOnClose
      >
        <Paragraph>{t("network.confirmBody")}</Paragraph>
        {!safeMode ? (
          <Alert
            type="error"
            showIcon
            message={t("network.confirmUnsafeWarning")}
          />
        ) : null}
        <div className={styles.passwordField}>
          <Text>{t("network.passwordLabel")}</Text>
          <Input.Password
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("network.passwordPlaceholder")}
            autoComplete="current-password"
            data-testid="tunnel-password"
          />
          <Text type="secondary">{t("network.passwordHelp")}</Text>
        </div>
      </Modal>
    </PageShell>
  );
}
