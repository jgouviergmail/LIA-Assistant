'use client';

/**
 * LabelsManager — the person's own Gmail labels, created, renamed, deleted
 * (ADR-369, spec §6.3: Gmail only; system labels are never listed, so never
 * offered). « / » in a name nests it under another, as Gmail does. Deleting a
 * label keeps its messages — the confirmation says so. A name already taken is
 * said in the refusal's own words.
 */
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useConfirm } from '@/components/ui/use-confirm';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailFolder } from '@/lib/workbench/types';

export interface LabelsManagerProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  labels: readonly MailFolder[];
  /** Each act rejects when refused (the screen says why); it resolves once done. */
  onCreate: (name: string) => Promise<void>;
  onRename: (labelId: string, name: string) => Promise<void>;
  onDelete: (labelId: string) => Promise<void>;
}

export function LabelsManager({
  lng,
  open,
  onOpenChange,
  labels,
  onCreate,
  onRename,
  onDelete,
}: LabelsManagerProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const newId = useId();
  const renameField = useRef<HTMLInputElement>(null);
  const editingId = editing?.id ?? null;

  // The field that replaces a label's name takes the focus the pencil had.
  useEffect(() => {
    if (editingId !== null) renameField.current?.focus();
  }, [editingId]);

  const run = async (id: string, act: () => Promise<void>) => {
    if (busy !== null) return false;
    setBusy(id);
    try {
      await act();
      return true;
    } catch {
      // Said by the screen; the field keeps what was typed.
      return false;
    } finally {
      setBusy(null);
    }
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    const wanted = name.trim();
    if (!wanted) return;
    if (await run('new', () => onCreate(wanted))) setName('');
  };

  const rename = async (event: FormEvent) => {
    event.preventDefault();
    const target = editing;
    if (!target || !target.name.trim()) return;
    if (await run(target.id, () => onRename(target.id, target.name.trim()))) setEditing(null);
  };

  const remove = async (label: MailFolder) => {
    const confirmed = await confirm({
      title: t('workbench.mail.labels.delete_title', { name: label.name ?? '' }),
      description: t('workbench.mail.labels.delete_description'),
      confirmLabel: t('common.delete'),
    });
    if (confirmed) await run(label.id, () => onDelete(label.id));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('workbench.mail.manage_labels')}</DialogTitle>
          <DialogDescription>{t('workbench.mail.labels.description')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={create} className="flex items-end gap-2">
          <Input
            id={newId}
            label={t('workbench.mail.labels.new')}
            value={name}
            onChange={event => setName(event.target.value)}
            className="flex-1"
          />
          <Button type="submit" isLoading={busy === 'new'} className="gap-1.5">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.labels.create')}
          </Button>
        </form>
        {labels.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('workbench.mail.no_labels')}</p>
        ) : (
          <ul className="max-h-80 divide-y overflow-y-auto rounded-md border">
            {labels.map(label =>
              editing?.id === label.id ? (
                <li key={label.id} className="px-3 py-2">
                  <form onSubmit={rename} className="flex items-end gap-2">
                    <Input
                      ref={renameField}
                      label={t('workbench.mail.labels.rename_field', { name: label.name ?? '' })}
                      value={editing.name}
                      onChange={event => setEditing({ id: label.id, name: event.target.value })}
                      className="flex-1"
                    />
                    <Button
                      type="submit"
                      size="icon"
                      isLoading={busy === label.id}
                      aria-label={t('workbench.mail.labels.save')}
                    >
                      <Check className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      onClick={() => setEditing(null)}
                      aria-label={t('common.cancel')}
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </form>
                </li>
              ) : (
                <li key={label.id} className="flex items-center gap-2 px-3 py-1.5">
                  <span className="min-w-0 flex-1 truncate text-sm">{label.name}</span>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={() => setEditing({ id: label.id, name: label.name ?? '' })}
                    aria-label={t('workbench.mail.labels.rename', { name: label.name ?? '' })}
                  >
                    <Pencil className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    isLoading={busy === label.id}
                    onClick={() => void remove(label)}
                    className="text-destructive hover:text-destructive"
                    aria-label={t('workbench.mail.labels.delete', { name: label.name ?? '' })}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </li>
              )
            )}
          </ul>
        )}
        {confirmDialog}
      </DialogContent>
    </Dialog>
  );
}
