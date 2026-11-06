'use client';

/**
 * What sending messages away does to the screen (ADR-369, lot 4).
 *
 * One way for the row, the selection, the reader, a drop and a key: the selection
 * keeps what did not leave, and an open message that left gives its place to the next
 * one on a large screen, or goes back to the list. Deleting for good asks first; the
 * person picks a folder in a dialog the keyboard reaches.
 */
import { useState, type ReactNode } from 'react';

import { useConfirm } from '@/components/ui/use-confirm';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  actOfDrop,
  movesFrom,
  nextAfter,
  type MailMoves,
  type MailSendAct,
} from '@/lib/workbench/mail';
import type { MailFolder, MailSummary } from '@/lib/workbench/types';

import type { ListSelection } from '../useListSelection';
import type { MailActs } from './useMailActs';
import type { MailAddress } from './useMailScreen';

export interface MailSending {
  /** What the open folder offers. */
  moves: MailMoves;
  send: (ids: readonly string[], act: MailSendAct, to?: string) => Promise<void>;
  /** What a drop on a folder of the pane does. */
  drop: (ids: readonly string[], folder: string) => void;
  /** The messages the folder picker is open for. */
  moving: readonly string[] | null;
  startMove: (ids: readonly string[]) => void;
  stopMove: () => void;
  pickFolder: (folderId: string) => void;
  forever: (ids: readonly string[]) => Promise<void>;
  /** Asks, then empties the trash. */
  empty: () => Promise<void>;
  /** The question, for the screen to draw. */
  confirmDialog: ReactNode;
}

export interface MailSendingOptions {
  lng: Language;
  acts: MailActs;
  address: MailAddress;
  rows: readonly MailSummary[];
  selection: ListSelection;
  folders: readonly MailFolder[] | undefined;
  permanentDelete: boolean;
  /** On a large screen an open message that left gives its place to the next one. */
  desktop: boolean;
}

export function useMailSending({
  lng,
  acts,
  address,
  rows,
  selection,
  folders,
  permanentDelete,
  desktop,
}: MailSendingOptions): MailSending {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [moving, setMoving] = useState<readonly string[] | null>(null);
  const { openId } = address;

  /** Runs an act that takes messages away, then lets go of what left. */
  const leaving = async (ids: readonly string[], act: () => Promise<readonly string[]>) => {
    const staying = rows.filter(row => row.id === openId || !ids.includes(row.id));
    const next = desktop && openId && ids.includes(openId) ? nextAfter(staying, openId) : null;
    const done = await act();
    selection.select(new Set([...selection.selected].filter(id => !done.includes(id))));
    if (!openId || !done.includes(openId)) return;
    if (next) address.replaceMessage(next);
    else address.closeMessage();
  };

  const send: MailSending['send'] = (ids, act, to) => leaving(ids, () => acts.send(ids, act, to));

  return {
    moves: movesFrom(address.folder, folders, permanentDelete),
    send,
    drop: (ids, folder) => void send(ids, actOfDrop(folder), folder),
    moving,
    startMove: setMoving,
    stopMove: () => setMoving(null),
    pickFolder: folderId => {
      const ids = moving;
      setMoving(null);
      if (ids) void send(ids, 'move', folderId);
    },
    forever: async ids => {
      const agreed = await confirm({
        title: t('workbench.mail.delete_forever_title', { count: ids.length }),
        description: t('workbench.mail.delete_forever_description'),
        confirmLabel: t('workbench.mail.delete_forever'),
      });
      if (agreed) await leaving(ids, () => acts.deleteForever(ids));
    },
    empty: async () => {
      const agreed = await confirm({
        title: t('workbench.mail.empty_trash_title'),
        description: t('workbench.mail.empty_trash_description'),
        confirmLabel: t('workbench.mail.empty_trash'),
      });
      if (agreed) await acts.emptyTrash();
    },
    confirmDialog,
  };
}
