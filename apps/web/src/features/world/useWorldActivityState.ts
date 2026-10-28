'use client';
import { useState } from 'react';
import { WORKSPACE_SELECTION, type ActivityEntry, type WorldSelection } from './activity-entry';

export interface WorldActivityEntry extends Omit<ActivityEntry, 'selection'> {
  selection: WorldSelection | null;
}
export type WorldActivityContext = Omit<WorldActivityEntry, 'selection'>;
interface State {
  seatKey: string | null;
  enabled: boolean;
  generation: number;
  dashboardStarted: boolean;
  entry: WorldActivityEntry;
  history: readonly WorldActivityEntry[];
}
function withEntry(state: State, entry: WorldActivityEntry): State {
  const dashboard = entry.selection === WORKSPACE_SELECTION.dashboard;
  if (dashboard && state.seatKey === null) return state;
  return { ...state, entry, dashboardStarted: state.dashboardStarted || dashboard };
}
/** A new seating starts a fresh dashboard; a loss of authority closes what was open but
 *  keeps the seated dashboard, whose paid synthesis must survive Discuter or home editing. */
function synchronized(state: State, seatKey: string | null, enabled: boolean): State {
  let next = state;
  if (next.seatKey !== seatKey)
    next = {
      ...next,
      seatKey,
      generation: next.generation + 1,
      dashboardStarted: false,
      entry:
        next.entry.selection === WORKSPACE_SELECTION.dashboard ? { selection: null } : next.entry,
      history: next.history.filter(item => item.selection !== WORKSPACE_SELECTION.dashboard),
    };
  if (next.enabled !== enabled)
    next = enabled
      ? { ...next, enabled }
      : {
          ...next,
          enabled,
          generation: next.generation + 1,
          entry: { selection: null },
          history: [],
        };
  return next;
}
/** Atomic private navigation: bounded payload history and one retained dashboard per seating. */
export function useWorldActivityState(seatKey: string | null, enabled = true) {
  const [state, setState] = useState<State>({
    seatKey,
    enabled,
    generation: 0,
    dashboardStarted: false,
    entry: { selection: null },
    history: [],
  });
  if (state.seatKey !== seatKey || state.enabled !== enabled)
    setState(synchronized(state, seatKey, enabled));
  const generation = state.generation;
  const update = (transition: (current: State) => State) => {
    setState(current => (current.generation === generation ? transition(current) : current));
  };
  return {
    entry: state.entry,
    history: state.history,
    dashboardStarted: state.dashboardStarted,
    activate(entry: WorldActivityEntry) {
      update(current => {
        const next = withEntry(current, entry);
        return next === current ? current : { ...next, history: [] };
      });
    },
    navigate(selection: WorldSelection, context: WorldActivityContext = {}) {
      update(current => {
        const next = withEntry(current, { selection, ...context });
        if (next === current) return current;
        const history =
          current.entry.selection && selection !== current.entry.selection
            ? [...current.history, current.entry].slice(-16)
            : current.history;
        return { ...next, history };
      });
    },
    back() {
      update(current => ({
        ...withEntry(current, current.history.at(-1) ?? { selection: 'catalogue' }),
        history: current.history.slice(0, -1),
      }));
    },
    close() {
      update(current => withEntry(current, { selection: null }));
    },
    complete(selection: WorldSelection) {
      update(current =>
        current.entry.selection === selection ? withEntry(current, { selection: null }) : current
      );
    },
  };
}
