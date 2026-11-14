'use client';

/**
 * LabelMenu — the person's Gmail labels on one message or a selection
 * (ADR-369, spec §6.3: Gmail only, the descriptor's `labels`).
 *
 * Each label is a checkbox item that states what is true now — checked when
 * every message carries it, mixed when some do — and a choice applies it to
 * all of them, or takes it off all of them when all carried it. The lines are
 * the same under the reader's own icon (`LabelMenu`) and under the line of a
 * selection's list (`LabelLines`).
 */
import { Tag } from '@/lib/icons';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { labelState } from '@/lib/workbench/mail';
import type { MailFolder } from '@/lib/workbench/types';

export interface LabelLinesProps {
  lng: Language;
  /** The person's labels (the pane's own folders). */
  labels: readonly MailFolder[];
  messages: readonly { label_ids: readonly string[] }[];
  onApply: (add: string[], remove: string[]) => void;
  /** An act is on its way: the lines take nothing. */
  busy?: boolean;
}

/** The labels as lines of a menu, each stating what is true of the messages now. */
export function LabelLines({ lng, labels, messages, onApply, busy = false }: LabelLinesProps) {
  const { t } = useTranslation(lng);
  if (labels.length === 0) {
    return <DropdownMenuItem disabled>{t('workbench.mail.no_labels')}</DropdownMenuItem>;
  }
  return (
    <>
      {labels.map(label => {
        const state = labelState(messages, label.id);
        return (
          <DropdownMenuCheckboxItem
            key={label.id}
            checked={state === 'all' ? true : state === 'some' ? 'indeterminate' : false}
            onSelect={() => {
              if (busy) return;
              if (state === 'all') onApply([], [label.id]);
              else onApply([label.id], []);
            }}
          >
            {label.name}
          </DropdownMenuCheckboxItem>
        );
      })}
    </>
  );
}

/** The labels under their own icon, in the reader's toolbar. */
export function LabelMenu({ busy = false, ...lines }: LabelLinesProps) {
  const { t } = useTranslation(lines.lng);
  const title = t('workbench.mail.labels_title');
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={title}
          aria-disabled={busy || undefined}
        >
          <Tag className="h-4 w-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{title}</DropdownMenuLabel>
        <LabelLines busy={busy} {...lines} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
