import { describe, expect, it } from "vitest";

import {
  CHECKLIST_DISMISSED_KEY,
  checklistComplete,
  checklistSteps,
} from "./FirstRunChecklist";
import type { Session } from "../hooks/useSessions";

const t = (key: string) => key;

const session = (hasActivity?: boolean): Session =>
  ({ id: "t1", name: "t", threadId: "t1", hasActivity }) as Session;

describe("first-run checklist", () => {
  it("marks every step undone for a brand-new install", () => {
    const steps = checklistSteps(
      { modelsReady: false, hasAgent: false, hasConversation: false },
      t,
    );
    expect(steps.map((step) => step.done)).toEqual([false, false, false]);
    expect(steps.map((step) => step.key)).toEqual([
      "model",
      "agent",
      "conversation",
    ]);
  });

  it("ticks steps independently, in order", () => {
    const steps = checklistSteps(
      { modelsReady: true, hasAgent: true, hasConversation: false },
      t,
    );
    expect(steps.map((step) => step.done)).toEqual([true, true, false]);
  });

  it("is complete only when all three are done", () => {
    expect(
      checklistComplete({
        modelsReady: true,
        hasAgent: true,
        hasConversation: true,
      }),
    ).toBe(true);
    expect(
      checklistComplete({
        modelsReady: true,
        hasAgent: true,
        hasConversation: false,
      }),
    ).toBe(false);
  });

  it("does not count an empty thread as a conversation", () => {
    // Otherwise creating a chat would tick step three before the user typed.
    expect(
      checklistComplete({
        modelsReady: true,
        hasAgent: true,
        hasConversation: [session(undefined), session(false)].some(
          (s) => s.hasActivity,
        ),
      }),
    ).toBe(false);
    expect(
      checklistComplete({
        modelsReady: true,
        hasAgent: true,
        hasConversation: [session(true)].some((s) => s.hasActivity),
      }),
    ).toBe(true);
  });

  it("persists dismissal under a namespaced key", () => {
    expect(CHECKLIST_DISMISSED_KEY).toBe("octop:first-run-checklist-dismissed");
  });
});
