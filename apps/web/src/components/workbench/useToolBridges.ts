'use client';

/**
 * The ways from one tool to another (ADR-369, lot 2), and to LIA.
 *
 * A way out is offered where its tool is ready. What it carries is handed through
 * the page (`lib/workbench/handoff`), or left as a draft for the chat, which sends
 * nothing by itself: the person reads it and goes on from there.
 */
import type { Language } from '@/i18n/settings';
import { useHandoffNavigation } from '@/hooks/useHandoff';
import { HANDOFF_TOOLS, type HandoffKind, type WorkbenchHandoff } from '@/lib/workbench/handoff';

import { useWorkbench } from './WorkbenchShell';
import { useAskLia } from './assist/useAskLia';
import type { AssistDoors } from './assist/useAssistHost';

export interface ToolBridges extends AssistDoors {
  /** Whether a thing of this kind has somewhere to go. */
  offers: (kind: HandoffKind) => boolean;
  /** Opens its tool on it. */
  go: (handoff: WorkbenchHandoff) => void;
  /** Opens the chat on these words, unsent. */
  ask: (words: string) => void;
  /** A click may ask a model from here (ADR-372). */
  assists: boolean;
}

export function useToolBridges(lng: Language): ToolBridges {
  const { availability, doors, assists } = useWorkbench();
  const go = useHandoffNavigation(lng);
  const ask = useAskLia(lng);
  return {
    offers: kind =>
      availability.tools.some(item => item.tool === HANDOFF_TOOLS[kind] && item.state === 'ready'),
    go,
    ask,
    ...doors,
    assists,
  };
}
