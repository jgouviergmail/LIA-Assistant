import { useRef, useState } from 'react';
import type { TFunction } from 'i18next';

import { useApplicationAccountToast } from './useApplicationAccountToast';
import { useMCPBehaviorPreview, useMCPToolChoice } from './useMCPServerBehavior';
import type { MCPQuestionLoss, MCPToolChoice } from '@/lib/mcp-behavior';

interface PendingChoice {
  tool: string;
  choice: MCPToolChoice | null;
  losses: MCPQuestionLoss[];
}

/**
 * Choosing when LIA asks before ONE tool (spec 2026-10-30 D6, § 6).
 *
 * The choice is previewed first, like every level: one that makes LIA ask less waits
 * in `pending` — the API's own list of what LIA would no longer ask about — until the
 * person confirms; one that asks more is written at once. After a write the caller
 * re-reads the synthesis (`onApplied`). A choice made while another is being checked
 * is ignored, and `busy` says so.
 */
export function useMCPToolChoiceFlow(
  serverId: string,
  ownerId: string | undefined,
  onApplied: () => void,
  t: TFunction
) {
  const toast = useApplicationAccountToast(ownerId);
  const { previewServer } = useMCPBehaviorPreview();
  const { setToolChoice } = useMCPToolChoice();
  const [pending, setPending] = useState<PendingChoice | null>(null);
  const [busy, setBusy] = useState(false);
  // Two change events in one render both read `busy` false: the ref closes that gap.
  const inFlight = useRef(false);

  const hold = (value: boolean) => {
    inFlight.current = value;
    setBusy(value);
  };

  const write = async (tool: string, choice: MCPToolChoice | null) => {
    try {
      await setToolChoice(serverId, tool, choice);
      onApplied();
    } catch {
      toast.error(t('common.error'));
    }
  };

  const choose = async (tool: string, choice: MCPToolChoice | null) => {
    if (inFlight.current) return;
    hold(true);
    try {
      const preview = await previewServer(serverId, { tool_choices: { [tool]: choice } });
      if (preview && preview.questions_lost.length > 0)
        return setPending({ tool, choice, losses: preview.questions_lost });
      await write(tool, choice);
    } catch {
      toast.error(t('common.error'));
    } finally {
      hold(false);
    }
  };

  const confirm = async () => {
    if (!pending || inFlight.current) return;
    setPending(null);
    hold(true);
    try {
      await write(pending.tool, pending.choice);
    } finally {
      hold(false);
    }
  };

  return { choose, confirm, cancel: () => setPending(null), pending, busy };
}
