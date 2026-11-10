'use client';

/**
 * The messages on screen, by what they weigh (ADR-372).
 *
 * One chip among the list's chips, so a phone keeps it behind « Filters »: the page sorts what it
 * already shows, and nothing is asked until a line is chosen. The answer belongs to the rows it was
 * asked about: another page, or a refreshed one, starts over. What could not be read keeps its place
 * and is counted; what is held costs nothing.
 */
import { ChevronDown } from '@/lib/icons';
import { useState, type ReactNode } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { ASSIST_PATHS, type TriageAnswer, type TriagedMessage } from '@/lib/workbench/assist';
import type { MailLine } from '@/lib/workbench/mail';
import type { MailSummary } from '@/lib/workbench/types';

import { MAIL_CHIP } from '../mail/MailSearchBar';
import { useAssistBounds } from '../WorkbenchShell';
import { AssistStars } from '@/components/selection-assist/AssistStars';
import { tellCost, useToldFailure } from './tellings';
import { useAssistCall } from '@/hooks/useAssistCall';

/** How a page can be read by what it weighs. */
export type TriageMode = 'important' | 'category' | 'priority';

const MODES: readonly TriageMode[] = ['important', 'category', 'priority'];
const IMPORTANCE: Readonly<Record<string, number>> = { high: 0, normal: 1, low: 2 };
const CATEGORIES: readonly string[] = [
  'work',
  'personal',
  'transactional',
  'notification',
  'newsletter',
  'other',
];

type Known = ReadonlyMap<string, TriagedMessage>;

function importanceOf(line: MailLine, known: Known): number {
  return IMPORTANCE[known.get(line.message.id)?.importance ?? 'normal'] ?? IMPORTANCE.normal;
}

function categoryOf(line: MailLine, known: Known): number {
  const category = known.get(line.message.id)?.category ?? 'other';
  const rank = CATEGORIES.indexOf(category);
  return rank < 0 ? CATEGORIES.length : rank;
}

/**
 * @param lines - The lines, in the mailbox's order.
 * @param known - What each message weighs.
 * @param mode - How they are read.
 * @returns The lines to show: a sort keeps the mailbox's order among equals.
 */
export function triagedLines(
  lines: readonly MailLine[],
  known: Known,
  mode: TriageMode
): readonly MailLine[] {
  if (mode === 'priority') return lines.filter(line => importanceOf(line, known) === 0);
  const rank = mode === 'category' ? categoryOf : importanceOf;
  return [...lines].sort((one, other) => rank(one, known) - rank(other, known));
}

export interface MailTriage {
  /** The lines the screen shows. */
  lines: readonly MailLine[];
  /** What a row says of its kind, sorted by kind. */
  noteOf: (message: MailSummary) => string | undefined;
  /** The chip; nothing where a click may not ask a model. */
  chip: ReactNode;
  /** It narrows or orders what is shown. */
  on: boolean;
}

/**
 * @param lng - The reader's language.
 * @param lines - The lines, in the mailbox's order.
 * @param pageSize - How many messages one answer weighs.
 * @returns What the list shows, and the chip that changes it.
 */
export function useMailTriage(
  lng: Language,
  lines: readonly MailLine[],
  pageSize: number
): MailTriage {
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  const scope = lines.map(line => line.message.id).join('|');
  const call = useAssistCall<TriageAnswer>(scope);
  const [chosen, setChosen] = useState<{ scope: string; mode: TriageMode } | null>(null);
  useToldFailure(lng, call.state);
  const answer = call.state.status === 'done' ? call.state.value : null;
  const mode = answer && chosen?.scope === scope ? chosen.mode : null;
  const known: Known = new Map(answer?.items.map(item => [item.id, item]));
  const running = call.state.status === 'running';

  const hasNone = (items: readonly TriagedMessage[], next: TriageMode) =>
    next === 'priority' && !items.some(item => item.importance === 'high');
  const settled = (next: TriageMode, items: readonly TriagedMessage[]) => {
    if (hasNone(items, next)) {
      toast.info(t('workbench.assist.triage.none_priority'));
      setChosen(null);
      return;
    }
    setChosen({ scope, mode: next });
  };
  const pick = async (next: TriageMode) => {
    if (answer) {
      settled(next, answer.items);
      return;
    }
    const weighed = await call.run(ASSIST_PATHS.mailTriage, {
      message_ids: lines.slice(0, pageSize).map(line => line.message.id),
    });
    if (!weighed) return;
    tellCost(weighed.usage);
    if (weighed.skipped > 0) {
      toast.info(t('workbench.assist.triage.skipped', { count: weighed.skipped }));
    }
    settled(next, weighed.items);
  };

  const label = t(mode ? `workbench.assist.triage.${mode}` : 'workbench.assist.triage.label');
  return {
    lines: mode ? triagedLines(lines, known, mode) : lines,
    noteOf: message => {
      const category = known.get(message.id)?.category;
      if (mode !== 'category' || !category) return undefined;
      return t(`workbench.assist.triage.categories.${category}`, {
        defaultValue: t('workbench.assist.triage.categories.other'),
      });
    },
    on: mode !== null,
    chip: bounds && lines.length > 0 && (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-pressed={mode !== null}
            aria-busy={running || undefined}
            isLoading={running}
            className={cn(MAIL_CHIP, 'gap-1.5')}
          >
            <AssistStars className="h-3.5 w-3.5" aria-hidden="true" />
            {label}
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuRadioGroup
            value={mode ?? ''}
            onValueChange={value => {
              const next = MODES.find(item => item === value);
              if (next) void pick(next);
            }}
          >
            {MODES.map(item => (
              <DropdownMenuRadioItem key={item} value={item}>
                {t(`workbench.assist.triage.${item}`)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          {mode && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setChosen(null)}>
                {t('workbench.assist.triage.mailbox_order')}
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  };
}
