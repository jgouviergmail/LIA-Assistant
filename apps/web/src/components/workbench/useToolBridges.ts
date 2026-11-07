'use client';

/**
 * The ways from one tool to another (ADR-369, lot 2), and to LIA.
 *
 * A way out is offered where its tool is ready. What it carries is handed through
 * the page (`lib/workbench/handoff`), or left as a draft for the chat, which sends
 * nothing by itself: the person reads it and goes on from there.
 */
import { useRouter } from 'next/navigation';
import { useEffect, useEffectEvent } from 'react';

import type { Language } from '@/i18n/settings';
import {
  handOff,
  takeHandoff,
  type HandoffKind,
  type WorkbenchHandoff,
} from '@/lib/workbench/handoff';
import { toolPath } from '@/lib/workbench/tools';
import type { WorkbenchToolId } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import { useWorkbench } from './WorkbenchShell';
import { useAskLia } from './assist/useAskLia';
import type { AssistDoors } from './assist/useAssistHost';

/** The tool each thing opens in. */
const DESTINATIONS: Readonly<Record<HandoffKind, WorkbenchToolId>> = {
  task: 'tasks',
  event: 'calendar',
  contact: 'contacts',
  compose: 'mail',
};

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
  const router = useRouter();
  const ask = useAskLia(lng);
  return {
    offers: kind =>
      availability.tools.some(item => item.tool === DESTINATIONS[kind] && item.state === 'ready'),
    go: handoff => {
      handOff(handoff);
      router.push(buildLocalizedPath(toolPath(DESTINATIONS[handoff.kind]), lng));
    },
    ask,
    ...doors,
    assists,
  };
}

/**
 * Takes what another tool handed this one, once the screen can show it.
 *
 * @param kind - What this tool takes.
 * @param ready - The screen can show it.
 * @param receive - What to do with it.
 */
export function useHandoff<K extends HandoffKind>(
  kind: K,
  ready: boolean,
  receive: (handoff: Extract<WorkbenchHandoff, { kind: K }>) => void
): void {
  const received = useEffectEvent(receive);
  useEffect(() => {
    if (!ready) return;
    const handoff = takeHandoff(kind);
    if (handoff) received(handoff);
  }, [kind, ready]);
}
