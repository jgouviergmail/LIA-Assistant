'use client';

/**
 * TaskQuickAdd — a task added with its title alone (ADR-369).
 *
 * One key per SUBMISSION: kept until the task is made, so a second click after
 * a lost answer is told what became of the first instead of making a second
 * task (the API answers `already_submitted`); a new key only once it is made.
 * What was typed stays when the act is refused, so nothing has to be retyped. Where LIA may be
 * asked, an icon inside the field reads a sentence: its title lands in the field, its day and list
 * in one line under it, and nothing exists until « Add » is pressed.
 */
import { Plus, X } from '@/lib/icons';
import { forwardRef, useState, type FormEvent, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ProposedTask } from '@/lib/workbench/assist';
import { cn, generateUUID } from '@/lib/utils';
import type { LLMUsage } from '@/types/llm-usage';

/** What LIA read in a sentence, beside its title. */
export interface TaskDetailsRead {
  due?: string;
  listName?: string;
  notes?: string;
}

/** LIA, inside the field. */
export interface QuickAddAssist {
  /** The icon, given what is typed and where its answer goes. */
  icon: (typed: string, onRead: (task: ProposedTask, usage: LLMUsage | null) => void) => ReactNode;
  /** A day, as the line under the field says it. */
  dayLabel: (day: string) => string;
}

export interface TaskQuickAddProps {
  lng: Language;
  /** The input's i18n label key and placeholder key (a task, or a subtask). */
  labelKey: string;
  placeholderKey: string;
  /** The longest title the provider takes (published bound). */
  maxLength?: number;
  /** A title already there, for the person to confirm. */
  initialTitle?: string;
  /** Make the task; resolves when it is made, rejects when refused. */
  onAdd: (title: string, idempotencyKey: string, read?: TaskDetailsRead) => Promise<void>;
  className?: string;
  /** Left out where a sentence is only a title. */
  assist?: QuickAddAssist;
}

export const TaskQuickAdd = forwardRef<HTMLInputElement, TaskQuickAddProps>(function TaskQuickAdd(
  { lng, labelKey, placeholderKey, maxLength, initialTitle = '', onAdd, className, assist },
  ref
) {
  const { t } = useTranslation(lng);
  const [title, setTitle] = useState(initialTitle);
  const [busy, setBusy] = useState(false);
  // Minted once (lazily), renewed only once a task is made.
  const [key, setKey] = useState(() => generateUUID());
  const [read, setRead] = useState<{ details: TaskDetailsRead; usage: LLMUsage | null } | null>(
    null
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onAdd(trimmed, key, read?.details);
      setKey(generateUUID());
      setTitle('');
      setRead(null);
    } catch {
      // Said by the caller; what was typed, and the key, stay for a retry.
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className={cn('border-b px-4 py-3', className)}>
      <div className="flex gap-2">
        {/* The field's frame is what the row measures: bounded here, never by the input. */}
        <div className="relative min-w-0 flex-1">
          <Input
            ref={ref}
            type="text"
            value={title}
            maxLength={maxLength}
            aria-label={t(labelKey)}
            placeholder={t(placeholderKey)}
            className={assist ? 'pr-10' : undefined}
            onChange={event => setTitle(event.target.value)}
          />
          {assist && (
            <span className="absolute right-1 top-1/2 -translate-y-1/2">
              {assist.icon(title, (task, usage) => {
                setTitle(task.title);
                setRead({
                  details: {
                    due: task.due ?? undefined,
                    listName: task.list_name ?? undefined,
                    notes: task.notes || undefined,
                  },
                  usage,
                });
              })}
            </span>
          )}
        </div>
        <Button type="submit" isLoading={busy}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('workbench.tasks.add')}
        </Button>
      </div>
      {read && (
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {[read.details.due && assist?.dayLabel(read.details.due), read.details.listName]
            .filter(Boolean)
            .join(' · ')}
          {read.usage && <LLMUsageBadge usage={read.usage} />}
          <button
            type="button"
            aria-label={t('workbench.assist.tasks.drop_read')}
            className="rounded p-0.5 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setRead(null)}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </p>
      )}
    </form>
  );
});
