'use client';

/**
 * NewTaskListDialog — a task list created by name (ADR-369).
 *
 * The key of the submission is kept until the dialog closes: a second click
 * after a lost answer is told what became of the first, never makes a second
 * list. Closing (made, cancelled, dismissed) empties the form and mints the
 * next submission's key — in the handler, never in an effect. A refusal is said in the dialog's own
 * caller (a toast) and the name stays typed.
 */
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface NewTaskListDialogProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The longest name the provider takes (published bound). */
  maxLength?: number;
  /** Make the list; resolves when it is made, rejects when refused. */
  onCreate: (title: string, idempotencyKey: string) => Promise<void>;
}

export function NewTaskListDialog({
  lng,
  open,
  onOpenChange,
  maxLength,
  onCreate,
}: NewTaskListDialogProps) {
  const { t } = useTranslation(lng);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());

  const openChange = (next: boolean) => {
    if (!next) {
      setTitle('');
      setKey(crypto.randomUUID());
    }
    onOpenChange(next);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onCreate(trimmed, key);
      openChange(false);
    } catch {
      // Said by the caller; the name and the key stay for a retry.
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={openChange}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t('workbench.tasks.new_list')}</DialogTitle>
          </DialogHeader>
          <Input
            label={t('workbench.tasks.new_list_name')}
            value={title}
            maxLength={maxLength}
            onChange={event => setTitle(event.target.value)}
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => openChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" isLoading={busy}>
              {t('workbench.tasks.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
