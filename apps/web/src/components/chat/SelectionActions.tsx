'use client';

/**
 * SelectionActions — act on a selected passage of an assistant answer (C-02).
 *
 * Desktop: a small toolbar floats above the selection. Mobile (no hover, no
 * comfortable floating UI): a bottom sheet — home-made on purpose (arbitration
 * A2: no `vaul` dependency) and NON-modal in spirit: plain fixed positioning,
 * no scroll lock, no overlay — a modal Radix surface would re-break the sticky
 * header (ADR-171).
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
        'inline-flex items-center gap-1.5 rounded-md border border-border/40 bg-background/90',
        'px-2 py-1.5 text-xs font-medium text-foreground/90 hover:bg-muted/70 hover:text-primary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors',
        isNarrow && 'w-full justify-start px-3 py-2 text-sm'
      )}
    >
      <action.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {t(`chat.selection.actions.${action.key}`)}
    </button>
  ));

  if (isNarrow) {
    // Bottom sheet — fixed, no scroll lock, no overlay (ADR-171 doctrine).
    return (
      <div
        role="toolbar"
        aria-label={t('chat.selection.aria')}
        className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t border-x border-border/60 bg-popover p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-2xl motion-safe:animate-in motion-safe:slide-in-from-bottom-4 motion-safe:duration-200"
      >
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="min-w-0 truncate text-xs italic text-muted-foreground">“{quote}”</p>
          <button
            type="button"
            onClick={clearNativeSelection}
            aria-label={t('chat.selection.close')}
            className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1.5">{buttons}</div>
      </div>
    );
  }

  // Desktop: float above the selection, clamped to the viewport.
  const top = Math.max(8, snapshot.rect.top - 44);
  const left = Math.max(8, Math.min(snapshot.rect.left, window.innerWidth - 560));
  return (
    <div
      role="toolbar"
      aria-label={t('chat.selection.aria')}
      style={{ top, left }}
      className="fixed z-50 flex items-center gap-1 rounded-lg border border-border/60 bg-popover p-1 shadow-xl motion-safe:animate-in motion-safe:fade-in motion-safe:duration-150"
    >
      {buttons}
    </div>
  );
}
