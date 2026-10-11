import { useEffect, useState } from "react";
import { Button, Input, Modal, Segmented, Typography, message } from "antd";
import { useTranslation } from "react-i18next";

import { authApi } from "../../api/modules/auth";
import styles from "./ForgotPasswordModal.module.less";

type Platform = "linux" | "mac" | "windows" | "docker";

interface Recovery {
  available: boolean;
  username: string | null;
}

function CopyCommand({ text }: { text: string }) {
  return (
    <Typography.Paragraph copyable className={styles.command}>
      {text}
    </Typography.Paragraph>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ForgotPasswordModal({ open, onClose }: Props) {
  const { t } = useTranslation();
  const [platform, setPlatform] = useState<Platform>("linux");
  const [recovery, setRecovery] = useState<Recovery | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    authApi
      .getLocalRecovery()
      .then((next) => {
        if (!cancelled) setRecovery(next);
      })
      .catch(() => {
        if (!cancelled) setRecovery({ available: false, username: null });
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Unknown until the probe answers, so the terminal instructions stay put
  // rather than flickering out and back.
  const showForm = recovery?.available === true && recovery.username !== null;

  return (
    <Modal
      open={open}
      title={t("login.forgotPasswordTitle", "Reset password")}
      onCancel={onClose}
      footer={
        <Button type="primary" onClick={onClose}>
          {t("login.forgotPasswordOk", "Got it")}
        </Button>
      }
      width={520}
      centered
      destroyOnHidden
    >
      <div className={styles.body} data-testid="login-forgot-password">
        {showForm ? (
          <LocalResetForm
            username={recovery.username as string}
            onDone={onClose}
          />
        ) : (
          <>
            <p className={styles.help}>
              {t(
                "login.forgotPasswordHelp",
                "Ask an administrator to reset it under Users. If you manage this host, run the command below on the machine where zcagent is installed, using the same OS account that runs the service.",
              )}
            </p>
            <CopyCommand
              text={t(
                "login.forgotPasswordCommand",
                "octop user passwd <username> --password <new-password>",
              )}
            />
            <p className={styles.hint}>
              {t(
                "login.forgotPasswordHint",
                "You can omit --password to enter it interactively. New password: at least 8 characters with letters and digits.",
              )}
            </p>
            <Segmented<Platform>
              block
              value={platform}
              onChange={setPlatform}
              options={[
                { label: "Linux", value: "linux" },
                { label: "macOS", value: "mac" },
                { label: "Windows", value: "windows" },
                { label: "Docker", value: "docker" },
              ]}
            />
            <PlatformHelp platform={platform} />
          </>
        )}
      </div>
    </Modal>
  );
}

function LocalResetForm({
  username,
  onDone,
}: {
  username: string;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && password !== confirm;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await authApi.localReset(username, password);
      message.success(
        t("login.localResetDone", "Password reset — sign in with it now."),
      );
      onDone();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.platform} data-testid="login-local-reset">
      <p className={styles.help}>
        {t(
          "login.localResetHelp",
          "This is your own machine, so zcagent can reset the password here without a terminal.",
        )}
      </p>
      <div>
        <p className={styles.label}>
          {t("login.localResetAccount", "Account")}
        </p>
        <Input value={username} readOnly />
      </div>
      <div>
        <p className={styles.label}>
          {t("login.localResetNewPassword", "New password")}
        </p>
        <Input.Password
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t(
            "login.localResetPasswordPlaceholder",
            "At least 8 characters, letters and digits",
          )}
          autoComplete="new-password"
        />
      </div>
      <div>
        <p className={styles.label}>
          {t("login.localResetConfirm", "Confirm password")}
        </p>
        <Input.Password
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          status={mismatch ? "error" : undefined}
          autoComplete="new-password"
        />
      </div>
      {mismatch ? (
        <p className={styles.hint}>
          {t("login.localResetMismatch", "The two passwords do not match.")}
        </p>
      ) : null}
      {error ? <p className={styles.hint}>{error}</p> : null}
      <Button
        type="primary"
        block
        loading={busy}
        disabled={mismatch || password.length === 0}
        onClick={() => void submit()}
      >
        {t("login.localResetSubmit", "Reset password")}
      </Button>
      <p className={styles.hint}>
        {t(
          "login.localResetFootnote",
          "Only this computer can do this, and only while it holds a single account.",
        )}
      </p>
    </div>
  );
}

function PlatformHelp({ platform }: { platform: Platform }) {
  const { t } = useTranslation();

  if (platform === "docker") {
    return (
      <div className={styles.platform}>
        <p className={styles.note}>
          {t("login.forgotPasswordDocker", "Enter the container, then run:")}
        </p>
        <CopyCommand
          text={t(
            "login.forgotPasswordDockerCommand",
            "docker exec -it <container> octop user passwd <username> --password <new-password>",
          )}
        />
      </div>
    );
  }

  if (platform === "windows") {
    return (
      <div className={styles.platform}>
        <p className={styles.note}>
          {t(
            "login.forgotPasswordWindows",
            "Open PowerShell or Command Prompt, then run the command above. If octop is not found:",
          )}
        </p>
        <div className={styles.fallback}>
          <p className={styles.label}>PowerShell</p>
          <CopyCommand
            text={t(
              "login.forgotPasswordWindowsPs",
              '& "$env:USERPROFILE\\.octop\\bin\\octop.cmd" user passwd <username> --password <new-password>',
            )}
          />
          <p className={styles.label}>
            {t("login.forgotPasswordWindowsCmdLabel", "Command Prompt")}
          </p>
          <CopyCommand
            text={t(
              "login.forgotPasswordWindowsCmd",
              "%USERPROFILE%\\.octop\\bin\\octop.cmd user passwd <username> --password <new-password>",
            )}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.platform}>
      <p className={styles.note}>
        {platform === "mac"
          ? t(
              "login.forgotPasswordMac",
              "Open Terminal (Applications → Utilities → Terminal), then run the command above. If octop is not found:",
            )
          : t(
              "login.forgotPasswordLinux",
              "Open Terminal, then run the command above. If octop is not found:",
            )}
      </p>
      <CopyCommand
        text={t(
          "login.forgotPasswordUnixPath",
          "~/.octop/bin/octop user passwd <username> --password <new-password>",
        )}
      />
    </div>
  );
}
