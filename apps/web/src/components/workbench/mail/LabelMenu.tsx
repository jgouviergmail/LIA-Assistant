'use client';

/**
 * LabelMenu — the person's Gmail labels on one message or a selection
 * (ADR-369, spec §6.3: Gmail only, the descriptor's `labels`).
 *
 * Each label is a checkbox item that states what is true now — checked when
 * every message carries it, mixed when some do — and a choice applies it to
 * all of them, or takes it off all of them when all carried it.
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

export interface LabelMenuProps {
  lng: Language;
  /** The person's labels (the pane's own folders). */
  labels: readonly MailFolder[];
  messages: readonly { label_ids: readonly string[] }[];
  onApply: (add: string[], remove: string[]) => void;
  /** An act is on its way: the trigger states it and the menu takes nothing. */
  busy?: boolean;
  /** Draws the trigger as an icon alone (the reader's toolbar). */
  iconOnly?: boolean;
}

export function LabelMenu({
  lng,
  labels,
  messages,
  onApply,
  busy = false,
  iconOnly = false,
}: LabelMenuProps) {
  const { t } = useTranslation(lng);
  const title = t('workbench.mail.labels_title');
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant={iconOnly ? 'ghost' : 'outline'}
          size={iconOnly ? 'icon' : 'sm'}
          aria-label={iconOnly ? title : undefined}
          aria-disabled={busy || undefined}
          className={iconOnly ? undefined : 'gap-1.5'}
        >
          <Tag className="h-4 w-4" aria-hidden="true" />
          {!iconOnly && title}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{title}</DropdownMenuLabel>
        {labels.length === 0 ? (
          <DropdownMenuItem disabled>{t('workbench.mail.no_labels')}</DropdownMenuItem>
        ) : (
          labels.map(label => {
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
          })
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
