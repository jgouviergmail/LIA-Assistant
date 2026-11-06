'use client';

/**
 * MoveDialog — where a selection goes (ADR-369, lot 4).
 *
 * The keyboard's and the phone's way to what the mouse does by dragging a row to the
 * pane. The inbox and the archive first, then the person's own folders in their tree;
 * what is listed is not offered, nor is a view (`takesDrop`): a message sits in a
 * place, never in « the starred ». The trash and the spam have their own buttons.
 */
import { Folder, Inbox, Archive, Tag, type LucideIcon } from 'lucide-react';
import { useMemo } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { folderTree, MAIL_SPAM, MAIL_TRASH, takesDrop } from '@/lib/workbench/mail';
import type { MailFolder } from '@/lib/workbench/types';

import { useFolderName } from './FolderPane';

export interface MoveDialogProps {
  lng: Language;
  /** The messages that go; null keeps it closed. */
  moving: readonly string[] | null;
  folders: readonly MailFolder[] | undefined;
  /** What is listed. */
  listed: string;
  /** Gmail: the person's folders are labels. */
  labels: boolean;
  onPick: (folderId: string) => void;
  onClose: () => void;
}

/** The system places the picker offers: the trash and the spam have their own buttons. */
function isOffered(folder: MailFolder, listed: string): boolean {
  return takesDrop(folder, listed) && folder.id !== MAIL_TRASH && folder.id !== MAIL_SPAM;
}

export function MoveDialog({
  lng,
  moving,
  folders,
  listed,
  labels,
  onPick,
  onClose,
}: MoveDialogProps) {
  const { t } = useTranslation(lng);
  const nameOf = useFolderName(lng);
  const destinations = useMemo(() => {
    const offered = (folders ?? []).filter(folder => isOffered(folder, listed));
    const own = offered.filter(folder => folder.kind === 'user');
    return [
      ...offered
        .filter(folder => folder.kind === 'system')
        .map(folder => ({ folder, name: null, depth: 0 })),
      ...folderTree(own, lng),
    ];
  }, [folders, listed, lng]);
  const iconOf = (folder: MailFolder): LucideIcon => {
    if (folder.role === 'inbox') return Inbox;
    if (folder.role === 'archive') return Archive;
    return labels ? Tag : Folder;
  };
  return (
    <Dialog open={moving !== null} onOpenChange={open => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('workbench.mail.move_title', { count: moving?.length ?? 0 })}
          </DialogTitle>
          <DialogDescription>{t('workbench.mail.move_description')}</DialogDescription>
        </DialogHeader>
        {destinations.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('workbench.mail.move_nowhere')}</p>
        ) : (
          <ul className="max-h-80 space-y-0.5 overflow-y-auto">
            {destinations.map(({ folder, name, depth }) => {
              const Icon = iconOf(folder);
              return (
                <li key={folder.id}>
                  <Button
                    variant="ghost"
                    // What the eye reads from its place, the ear is told whole.
                    aria-label={depth > 0 ? (folder.name ?? undefined) : undefined}
                    className="w-full justify-start gap-2"
                    style={{ paddingInlineStart: `${0.75 + Math.min(depth, 4) * 0.75}rem` }}
                    onClick={() => onPick(folder.id)}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="min-w-0 truncate">{name ?? nameOf(folder)}</span>
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
