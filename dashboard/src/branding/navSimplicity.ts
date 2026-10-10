import { useSyncExternalStore } from "react";

/**
 * Progressive disclosure for the sidebar.
 *
 * zcagent v1 ships as an internal, single-machine assistant. A handful of
 * upstream entries are cross-instance or POSIX-first surfaces that are dead
 * ends in that deployment, so they start hidden behind one switch instead of
 * being deleted -- deleting them would cost a merge conflict per release and
 * take capability away from deployments that do want them.
 */

const STORAGE_KEY = "***";
const CHANGED_EVENT = "zcagent:nav-full-changed";

/** Nav keys that only appear once "show all features" is on. */
export const ADVANCED_NAV_KEYS: ReadonlySet<string> = new Set([
  "bridge", // 云端协同 (BETA) -- talks to another instance
  "remote-desktop", // host desktop control -- POSIX-first
  "acp", // delegating to external coding agents
  "token-usage", // admin reporting
  "admin-storage", // remote workspace backends
]);

type NavLike = { items: readonly { key: string }[] };

function read(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setFullNavEnabled(on: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    /* private mode / disabled storage: the setting just won't persist */
  }
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

function subscribe(cb: () => void): () => void {
  window.addEventListener(CHANGED_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function useFullNavEnabled(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}

export function filterAdvancedNav<T extends NavLike>(
  sections: T[],
  showAll: boolean,
): T[] {
  if (showAll) return sections;
  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => !ADVANCED_NAV_KEYS.has(item.key)),
    }))
    .filter((section) => section.items.length > 0);
}
