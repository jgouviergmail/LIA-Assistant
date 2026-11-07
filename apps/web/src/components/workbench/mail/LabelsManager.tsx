'use client';

/**
 * LabelsManager — the person's own Gmail labels, Outlook's and iCloud's folders, or
 * calendars, created, renamed, deleted (ADR-369, spec §6.3, lots 4 and 5; what the
 * provider keeps for itself is never listed, so never offered). « / » in a label's
 * or a folder's name nests it under another. Deleting a label keeps its messages, a
 * folder holding anything is refused, and a calendar takes its events with it: the
 * confirmation says which. A folder's rename gives it a new own name, never a new
 * place, so its field holds that name alone. A name already taken is said in the
 * refusal's own words.
 */
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MailFolder } from '@/lib/workbench/types';
import { ToolDialogHeader, useToolConfirm } from '../ToolForm';

export interface LabelsManagerProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  labels: readonly Pick<MailFolder, 'id' | 'name'>[];
  /** What it manages, which decides its words: Gmail's labels by default. */
  kind?: ManagedKind;
  /** The longest name the provider keeps; left out, the provider says. */
  maxLength?: number;
  /** Each act rejects when refused (the screen says why); it resolves once done. */
  onCreate: (name: string) => Promise<void>;
  onRename: (labelId: string, name: string) => Promise<void>;
  onDelete: (labelId: string) => Promise<void>;
}

export type ManagedKind = 'labels' | 'folders' | 'calendars';

/** Where each kind's words live, and the two it says outside them. */
const WORDS: Readonly<Record<Exclude<ManagedKind, 'labels'>, Record<string, string>>> = {
  folders: {
    prefix: 'workbench.mail.folder_manager.',
    'workbench.mail.manage_labels': 'workbench.mail.manage_folders',
    'workbench.mail.no_labels': 'workbench.mail.folder_manager.none',
  },
  calendars: {
    prefix: 'workbench.calendar.manager.',
    'workbench.mail.manage_labels': 'workbench.calendar.manage_calendars',
    'workbench.mail.no_labels': 'workbench.calendar.manager.none',
  },
};

function wordOf(kind: ManagedKind, key: string): string {
  if (kind === 'labels') return key;
  const words = WORDS[kind];
  return words[key] ?? key.replace('workbench.mail.labels.', words.prefix);
}

/** What a rename starts from: a folder's own name, or a whole label's or calendar's. */
function editableName(label: Pick<MailFolder, 'name'>, kind: ManagedKind): string {
  const name = label.name ?? '';
  return kind === 'folders' ? name.slice(name.lastIndexOf('/') + 1) : name;
}

export function LabelsManager({
  lng,
  open,
  onOpenChange,
  labels,
  kind = 'labels',
  maxLength,
  onCreate,
  onRename,
  onDelete,
}: LabelsManagerProps) {
  const { t: translate } = useTranslation(lng);
  /** The manager's words: its kind's. */
  const t = (key: string, values?: Record<string, string>) => translate(wordOf(kind, key), values);
  const { confirm, confirmDialog } = useToolConfirm();
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

  const remove = async (label: Pick<MailFolder, 'id' | 'name'>) => {
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
        <ToolDialogHeader>
          <DialogTitle>{t('workbench.mail.manage_labels')}</DialogTitle>
          <DialogDescription>{t('workbench.mail.labels.description')}</DialogDescription>
        </ToolDialogHeader>
        <form onSubmit={create} className="flex items-end gap-2">
          <Input
            id={newId}
            label={t('workbench.mail.labels.new')}
            value={name}
            maxLength={maxLength}
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
                      maxLength={maxLength}
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
                      className="text-destructive hover:text-destructive"
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
                    onClick={() => setEditing({ id: label.id, name: editableName(label, kind) })}
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
