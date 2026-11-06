'use client';

/**
 * ContactGroupActions — the group chosen in the filter, renamed or deleted (ADR-369, lot 9).
 *
 * Deleting a group never deletes its contacts, and the person is told so before they answer. A
 * group a provider keeps for itself offers neither.
 */
import { Pencil, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useConfirm } from '@/components/ui/use-confirm';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchContactGroup } from '@/lib/workbench/types';

export interface ContactGroupActionsProps {
  lng: Language;
  group: WorkbenchContactGroup;
  nameMax: number | undefined;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  /** The group is gone: the list goes back to everyone. */
  onDeleted: () => void;
}

export function ContactGroupActions({
  lng,
  group,
  nameMax,
  onRename,
  onDelete,
  onDeleted,
}: ContactGroupActionsProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(group.name);
  const [busy, setBusy] = useState(false);

  const say = (error: unknown) => {
    const refusal = workbenchRefusal(error);
    toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed'));
  };

  const rename = async (event: FormEvent) => {
    event.preventDefault();
    const wanted = name.trim();
    if (!wanted || busy) return;
    setBusy(true);
    try {
      await onRename(group.id, wanted);
      setRenaming(false);
    } catch (error: unknown) {
      say(error);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    const confirmed = await confirm({
      title: t('workbench.contacts.groups.delete_title', { name: group.name }),
      description: t('workbench.contacts.groups.delete_description'),
      confirmLabel: t('common.delete'),
    });
    if (!confirmed) return;
    try {
      await onDelete(group.id);
      onDeleted();
    } catch (error: unknown) {
      say(error);
    }
  };

  return (
    <div className="flex justify-end gap-1">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        aria-label={t('workbench.contacts.groups.rename')}
        title={t('workbench.contacts.groups.rename')}
        onClick={() => {
          setName(group.name);
          setRenaming(true);
        }}
      >
        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-destructive hover:text-destructive"
        aria-label={t('workbench.contacts.groups.delete')}
        title={t('workbench.contacts.groups.delete')}
        onClick={() => void remove()}
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      {renaming && (
        <Dialog open onOpenChange={open => !open && setRenaming(false)}>
          <DialogContent className="sm:max-w-sm">
            <form onSubmit={rename} className="space-y-4">
              <DialogHeader>
                <DialogTitle>{t('workbench.contacts.groups.rename')}</DialogTitle>
              </DialogHeader>
              <Input
                label={t('workbench.contacts.groups.name')}
                value={name}
                maxLength={nameMax}
                required
                onChange={event => setName(event.target.value)}
              />
              <DialogFooter className="gap-2">
                <Button type="button" variant="outline" onClick={() => setRenaming(false)}>
                  {t('common.cancel')}
                </Button>
                <Button type="submit" isLoading={busy}>
                  {t('common.save')}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}
      {confirmDialog}
    </div>
  );
}
