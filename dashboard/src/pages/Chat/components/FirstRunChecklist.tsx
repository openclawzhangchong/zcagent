import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import StreamSetupGuide from "../../../components/StreamSetupGuide/StreamSetupGuide";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import type { Session } from "../hooks/useSessions";

export const CHECKLIST_DISMISSED_KEY = "octop:first-run-checklist-dismissed";

export interface ChecklistProgress {
  modelsReady: boolean;
  hasAgent: boolean;
  hasConversation: boolean;
}

/** Which of the three steps still need doing. Pure, so the ordering is testable. */
export function checklistSteps(
  progress: ChecklistProgress,
  t: (key: string) => string,
): { key: string; label: string; detail: string; done: boolean }[] {
  return [
    {
      key: "model",
      done: progress.modelsReady,
      label: t("firstRun.stepModel"),
      detail: t("firstRun.stepModelDetail"),
    },
    {
      key: "agent",
      done: progress.hasAgent,
      label: t("firstRun.stepAgent"),
      detail: t("firstRun.stepAgentDetail"),
    },
    {
      key: "conversation",
      done: progress.hasConversation,
      label: t("firstRun.stepChat"),
      detail: t("firstRun.stepChatDetail"),
    },
  ];
}

export function checklistComplete(progress: ChecklistProgress): boolean {
  return progress.modelsReady && progress.hasAgent && progress.hasConversation;
}

function readDismissed(): boolean {
  try {
    return localStorage.getItem(CHECKLIST_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

interface FirstRunChecklistProps {
  modelCount: number;
  noAgents: boolean;
  sessions: Session[];
  sessionsLoading: boolean;
}

export default function FirstRunChecklist({
  modelCount,
  noAgents,
  sessions,
  sessionsLoading,
}: FirstRunChecklistProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(readDismissed);

  const progress: ChecklistProgress = {
    modelsReady: modelCount > 0,
    hasAgent: !noAgents,
    // A thread the server has never seen content on does not count: an empty
    // placeholder would let the checklist vanish before the user typed anything.
    hasConversation: sessions.some((session) => session.hasActivity),
  };

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(CHECKLIST_DISMISSED_KEY, "1");
    } catch {
      /* storage disabled */
    }
    setDismissed(true);
  }, []);

  useEffect(() => {
    if (checklistComplete(progress) && !dismissed) {
      // Let the last step show as checked for a moment before it disappears.
      const timer = window.setTimeout(dismiss, 1600);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [
    dismissed,
    progress.hasAgent,
    progress.hasConversation,
    progress.modelsReady,
  ]);

  if (dismissed) return null;
  // While the thread list is still loading we cannot tell step three apart from
  // "no conversations yet", so stay quiet rather than flash a wrong state.
  if (sessionsLoading) return null;
  if (checklistComplete(progress)) return null;

  return (
    <StreamSetupGuide
      icon={<OctopEmptyMascot size={56} />}
      title={t("firstRun.title")}
      description={t("firstRun.description")}
      steps={checklistSteps(progress, t)}
      primaryAction={{
        label: progress.modelsReady
          ? t("firstRun.goExperts")
          : t("firstRun.goModels"),
        onClick: () =>
          navigate(progress.modelsReady ? "/experts" : "/admin/models"),
        type: "primary",
      }}
      onDismiss={dismiss}
      dismissLabel={t("firstRun.dismiss")}
    />
  );
}
