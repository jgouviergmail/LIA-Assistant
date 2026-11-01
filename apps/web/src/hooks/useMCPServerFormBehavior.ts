import { useCallback, useMemo, useState } from 'react';

import {
  confirmationChoiceOf,
  confirmationValueOf,
  driverOf,
  driverValues,
  type MCPBehaviorCandidates,
  type MCPConfirmationChoice,
  type MCPDriver,
  type MCPToolChoice,
  type UserMCPDefaults,
} from '@/lib/mcp-behavior';

/** The three stored values the form's two choices read and write. */
export interface MCPStoredBehavior {
  hitl_required: boolean | null;
  iterative_mode: boolean;
  react_expand_iterative: boolean | null;
}

/** A server that does not exist yet: like the account's strategy, driven directly. */
const NEW_SERVER: MCPStoredBehavior = {
  hitl_required: null,
  iterative_mode: false,
  react_expand_iterative: null,
};

const NO_DEFAULTS: Pick<
  UserMCPDefaults,
  'react_direct_tools_default' | 'dedicated_agents_available'
> = { react_direct_tools_default: true, dedicated_agents_available: true };

interface Choices {
  base: MCPStoredBehavior;
  startDriver: MCPDriver;
  confirmation: MCPConfirmationChoice;
  driver: MCPDriver;
  /** The tools' choices made in the form, by tool name; null returns one to the default. */
  toolChoices: Readonly<Record<string, MCPToolChoice | null>>;
}

function choicesFrom(
  stored: MCPStoredBehavior | null,
  defaults: UserMCPDefaults | undefined
): Choices {
  const base = stored ?? NEW_SERVER;
  const startDriver = driverOf(
    base.iterative_mode,
    base.react_expand_iterative,
    defaults ?? NO_DEFAULTS
  );
  return {
    base,
    startDriver,
    confirmation: confirmationChoiceOf(base.hitl_required),
    driver: startDriver,
    toolChoices: {},
  };
}

/**
 * The server form's confirmation, driver and per-tool choices (spec 2026-10-30 D3, D4,
 * D6; the tools' choices in the form by owner decision 2026-10-31).
 *
 * `candidates` is what saving would change — exactly what the preview judges and
 * exactly what the save adds to the form's other fields (it wins over the form's own
 * `iterative_mode`, which the settings page never edits). Its identity changes only
 * when a choice does. The ReAct shape is written only when the final driver differs
 * from where it started: an untouched shape stays NULL and keeps following the
 * instance default. A tool's choice is a candidate like the others: previewed with
 * them, alerted with them, written only when the form is saved.
 */
export function useMCPServerFormBehavior(
  stored: MCPStoredBehavior | null,
  defaults: UserMCPDefaults | undefined
) {
  const [choices, setChoices] = useState<Choices>(() => choicesFrom(stored, defaults));

  const reset = useCallback(
    (next: MCPStoredBehavior | null) => setChoices(choicesFrom(next, defaults)),
    [defaults]
  );
  const setConfirmation = useCallback(
    (confirmation: MCPConfirmationChoice) => setChoices(c => ({ ...c, confirmation })),
    []
  );
  const setDriver = useCallback((driver: MCPDriver) => setChoices(c => ({ ...c, driver })), []);
  const setToolChoice = useCallback(
    (toolName: string, choice: MCPToolChoice | null) =>
      setChoices(c => ({ ...c, toolChoices: { ...c.toolChoices, [toolName]: choice } })),
    []
  );

  const candidates = useMemo((): MCPBehaviorCandidates => {
    const out: MCPBehaviorCandidates = {};
    const confirmation = confirmationValueOf(choices.confirmation);
    if (confirmation !== choices.base.hitl_required) out.hitl_required = confirmation;
    if (choices.driver !== choices.startDriver) {
      const written = driverValues(choices.driver);
      if (written.iterative_mode !== choices.base.iterative_mode)
        out.iterative_mode = written.iterative_mode;
      if (
        written.react_expand_iterative !== undefined &&
        written.react_expand_iterative !== choices.base.react_expand_iterative
      )
        out.react_expand_iterative = written.react_expand_iterative;
    }
    if (Object.keys(choices.toolChoices).length > 0) out.tool_choices = choices.toolChoices;
    return out;
  }, [choices]);

  return {
    confirmation: choices.confirmation,
    driver: choices.driver,
    setConfirmation,
    setDriver,
    setToolChoice,
    reset,
    candidates,
  };
}
