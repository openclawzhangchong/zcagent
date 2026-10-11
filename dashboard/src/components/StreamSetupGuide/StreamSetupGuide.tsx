import type { ReactNode } from "react";
import { Button, Tooltip } from "antd";
import { Check, X } from "lucide-react";

import styles from "./StreamSetupGuide.module.less";

export interface SetupGuideStep {
  label: string;
  detail?: string;
  /** Renders a check instead of the number, for a step already completed. */
  done?: boolean;
}

export interface SetupGuideAction {
  label: ReactNode;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  type?: "primary" | "default";
  danger?: boolean;
  title?: string;
}

interface StreamSetupGuideProps {
  icon: ReactNode;
  title?: string;
  description?: string;
  steps: SetupGuideStep[];
  primaryAction?: SetupGuideAction;
  secondaryAction?: SetupGuideAction;
  /** Optional third action (e.g. uninstall) rendered after the main pair. */
  extraAction?: SetupGuideAction;
  className?: string;
  /** Widen the card for longer explanatory copy. */
  wide?: boolean;
  /**
   * Borderless tip layout (no card chrome), closer to Tasks empty state.
   * Prefer for page-level empty guides that sit directly in PageShell.
   */
  plain?: boolean;
  /** Shows a close affordance; for guides the user can opt out of permanently. */
  onDismiss?: () => void;
  dismissLabel?: string;
}

function ActionButton({ action }: { action: SetupGuideAction }) {
  const button = (
    <Button
      type={action.type ?? "primary"}
      danger={action.danger}
      icon={action.icon}
      loading={action.loading}
      disabled={action.disabled}
      onClick={action.onClick}
    >
      {action.label}
    </Button>
  );
  if (!action.title) return button;
  // Span wrapper so tooltips still work on disabled buttons.
  return (
    <Tooltip title={action.title}>
      <span>{button}</span>
    </Tooltip>
  );
}

export default function StreamSetupGuide({
  icon,
  title,
  description,
  steps,
  primaryAction,
  secondaryAction,
  extraAction,
  className,
  wide,
  plain,
  onDismiss,
  dismissLabel,
}: StreamSetupGuideProps) {
  const hasActions = primaryAction || secondaryAction || extraAction;
  const wrapClass = [
    styles.wrap,
    wide ? styles.wide : "",
    plain ? styles.plain : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={wrapClass}>
      <div className={styles.card}>
        {onDismiss ? (
          <Button
            type="text"
            size="small"
            className={styles.dismiss}
            icon={<X size={14} />}
            onClick={onDismiss}
            aria-label={dismissLabel}
            title={dismissLabel}
          />
        ) : null}
        <div className={styles.icon}>{icon}</div>
        {title ? <h3 className={styles.title}>{title}</h3> : null}
        {description ? (
          <p className={styles.description}>{description}</p>
        ) : null}
        {steps.length > 0 ? (
          <ol className={styles.steps}>
            {steps.map((step, index) => (
              <li key={index} className={styles.step}>
                <span
                  className={`${styles.stepIndex}${
                    step.done ? ` ${styles.stepIndexDone}` : ""
                  }`}
                >
                  {step.done ? <Check size={12} /> : index + 1}
                </span>
                <div className={styles.stepBody}>
                  <div
                    className={`${styles.stepLabel}${
                      step.done ? ` ${styles.stepLabelDone}` : ""
                    }`}
                  >
                    {step.label}
                  </div>
                  {step.detail ? (
                    <div className={styles.stepDetail}>{step.detail}</div>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : null}
        {hasActions ? (
          <div className={styles.actions}>
            {primaryAction ? <ActionButton action={primaryAction} /> : null}
            {secondaryAction ? <ActionButton action={secondaryAction} /> : null}
            {extraAction ? <ActionButton action={extraAction} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
