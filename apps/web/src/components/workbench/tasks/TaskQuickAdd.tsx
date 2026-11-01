'use client';

/**
 * TaskQuickAdd — a task added with its title alone (ADR-369).
 *
 * One key per SUBMISSION: kept until the task is made, so a second click after
 * a lost answer is told what became of the first instead of making a second
 * task (the API answers `already_submitted`); a new key only once it is made.
 * What was typed stays when the act is refused, so nothing has to be retyped.
 */
import { Plus } from 'lucide-react';
import { forwardRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';

export interface TaskQuickAddProps {
  lng: Language;
  /** The input's i18n label key and placeholder key (a task, or a subtask). */
  labelKey: string;
  placeholderKey: string;
  /** The longest title the provider takes (published bound). */
  maxLength?: number;
  /** Make the task; resolves when it is made, rejects when refused. */
  onAdd: (title: string, idempotencyKey: string) => Promise<void>;
  className?: string;
}

export const TaskQuickAdd = forwardRef<HTMLInputElement, TaskQuickAddProps>(function TaskQuickAdd(
  { lng, labelKey, placeholderKey, maxLength, onAdd, className },
  ref
) {
  const { t } = useTranslation(lng);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  // Minted once (lazily), renewed only once a task is made.
  const [key, setKey] = useState(() => crypto.randomUUID());

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onAdd(trimmed, key);
      setKey(crypto.randomUUID());
      setTitle('');
    } catch {
      // Said by the caller; what was typed, and the key, stay for a retry.
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className={cn('flex gap-2 border-b px-4 py-3', className)}>
      {/* The field's frame is what the row measures: bounded here, never by the input. */}
      <div className="min-w-0 flex-1">
        <Input
          ref={ref}
          type="text"
          value={title}
          maxLength={maxLength}
          aria-label={t(labelKey)}
          placeholder={t(placeholderKey)}
          onChange={event => setTitle(event.target.value)}
        />
      </div>
      <Button type="submit" isLoading={busy}>
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t('workbench.tasks.add')}
      </Button>
    </form>
  );
});
