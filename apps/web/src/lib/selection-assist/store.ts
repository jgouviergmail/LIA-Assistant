/** Ephemeral, account-owned selection. No text is persisted in browser storage or URLs. */
import { sameSelection, type SelectionTarget } from './targets';

export function createSelectionStore() {
  let target: SelectionTarget | null = null;
  let dismissed: SelectionTarget | null = null;
  let restoreFocus = true;
  const listeners = new Set<() => void>();
  const set = (next: SelectionTarget | null) => {
    if (next === target) return;
    if (next) restoreFocus = true;
    target = next;
    listeners.forEach(listener => listener());
  };
  return {
    getSnapshot: () => target,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    set,
    capture(next: SelectionTarget | null) {
      if (
        next &&
        dismissed &&
        next.element === dismissed.element &&
        (!next.text || sameSelection(next, dismissed))
      )
        return;
      if (next) dismissed = null;
      set(next);
    },
    dismiss(reason: 'explicit' | 'focus' = 'explicit') {
      restoreFocus = reason === 'explicit';
      dismissed = target;
      set(null);
    },
    shouldRestoreFocus: () => restoreFocus,
    beginInteraction() {
      dismissed = null;
    },
  };
}
export type SelectionStore = ReturnType<typeof createSelectionStore>;
