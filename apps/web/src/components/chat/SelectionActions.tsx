'use client';

/**
 * SelectionActions — act on a selected passage of an assistant answer (C-02).
 *
 * A measured, body-portaled toolbar stays beside the visible selection at
 * every screen size, outside the chat panel's filtered/clipping ancestors.
 * No scroll lock or overlay (ADR-171).
 *
 * Two safety rules learned elsewhere in this program:
 *  - the QUOTE comes from the React snapshot, never from `getSelection()` at
 *    click time — on iOS, tapping the sheet clears the selection first;
 *  - buttons preventDefault on pointer-down (the SlashCommandMenu trick) so
 *    the press does not collapse the selection before the click lands.
 *
 * Execute vs prefill follows ADR-173: named actions SEND through the normal
 * pipeline (HITL intact); "ask a question" PREFILLS — it needs the user's
 * own words.
 */

import { useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
  BookOpenText,
  Brain,
  CalendarPlus,
  Languages,
  ListPlus,
  MessageCircleQuestion,
  PenLine,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useTextSelection } from '@/hooks/useTextSelection';
import { useSelectionMenuPosition } from '@/hooks/useSelectionMenuPosition';
import { SELECTION_QUOTE_MAX_LENGTH } from '@/lib/constants';
import { cn } from '@/lib/utils';

interface SelectionActionDef {
  key: string;
  icon: LucideIcon;
  /** ADR-173: 'execute' sends through the pipeline, 'prefill' fills the composer. */
  mode: 'execute' | 'prefill';
}

const ACTIONS: readonly SelectionActionDef[] = [
  { key: 'explain', icon: BookOpenText, mode: 'execute' },
  { key: 'rephrase', icon: PenLine, mode: 'execute' },
  { key: 'translate', icon: Languages, mode: 'execute' },
  { key: 'to_task', icon: ListPlus, mode: 'execute' },
  { key: 'to_reminder', icon: CalendarPlus, mode: 'execute' },
  { key: 'remember', icon: Brain, mode: 'execute' },
  { key: 'ask', icon: MessageCircleQuestion, mode: 'prefill' },
];

/** Ellipsize the selection for the intent — a 4-page quote is noise. */
export function clampQuote(text: string, max: number = SELECTION_QUOTE_MAX_LENGTH): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function clearNativeSelection(): void {
  window.getSelection()?.removeAllRanges();
}

export interface SelectionActionsProps {
  /** The page's `sendMessageFromPresent` (ADR-173 execute path). */
  onExecute: (text: string) => void;
  /** The page's controlled prefill (`handleFollowupPick`). */
  onPrefill: (text: string) => void;
}

export function SelectionActions({ onExecute, onPrefill }: SelectionActionsProps) {
  const { t } = useTranslation();
  const isNarrow = useMediaQuery('(max-width: 639px)');
  const snapshot = useTextSelection();
  const menuRef = useSelectionMenuPosition(snapshot);

  // The quote is FROZEN from the snapshot the moment the menu rendered.
  const quote = useMemo(() => (snapshot ? clampQuote(snapshot.text) : ''), [snapshot]);

  if (!snapshot) return null;

  const runAction = (action: SelectionActionDef) => {
    const intent = t(`chat.selection.intents.${action.key}`, { quote });
    clearNativeSelection();
    if (action.mode === 'execute') {
      onExecute(intent);
    } else {
      onPrefill(intent);
    }
  };

  const buttons = ACTIONS.map(action => (
    <button
      key={action.key}
      type="button"
      // Land before the selection collapses (SlashCommandMenu trick).
      onMouseDown={event => event.preventDefault()}
      onClick={() => runAction(action)}
      className={cn(
        'inline-flex min-w-0 items-center gap-1.5 rounded-md border border-border/40 bg-background/90 [overflow-wrap:anywhere]',
        'px-2 py-1.5 text-xs font-medium text-foreground/90 hover:bg-muted/70 hover:text-primary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors',
        isNarrow && 'w-full justify-start px-3 py-2 text-sm'
      )}
    >
      <action.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {t(`chat.selection.actions.${action.key}`)}
    </button>
  ));

  return createPortal(
    <div
      ref={menuRef}
      role="toolbar"
      aria-label={t('chat.selection.aria')}
      style={{ visibility: 'hidden' }}
      className={cn(
        'fixed z-50 max-w-[calc(100vw-1rem)] overflow-auto overscroll-contain rounded-lg border border-border/60 bg-popover p-1 shadow-xl',
        isNarrow ? 'grid w-[22rem] grid-cols-2 gap-1.5' : 'flex w-max flex-wrap items-center gap-1'
      )}
    >
      {buttons}
      <button
        type="button"
        onMouseDown={event => event.preventDefault()}
        onClick={clearNativeSelection}
        aria-label={t('chat.selection.close')}
        className="min-w-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>,
    document.body
  );
}
