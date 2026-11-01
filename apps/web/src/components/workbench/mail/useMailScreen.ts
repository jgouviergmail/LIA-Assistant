'use client';

/**
 * The mail screen's small state machines (ADR-369, Task 4.7), each one job:
 *
 * - the ADDRESS: the open folder and message ride the query string — opening
 *   a message pushes, closing replaces, so « back » closes the reader;
 * - the SELECTION belongs to one listing: another folder, other words or other
 *   chips start with nothing selected (derived, never reset by an effect);
 * - the COMPOSER slot: each opening mounts a new composer, hence a new key;
 * - the LOOK: an unread message open for `MAIL_READ_DWELL_MS` is marked read;
 * - the DRAFTS' row acts: one draft opened at a time, each trash answered.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';

import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { WorkbenchMailDrafts } from '@/hooks/useWorkbenchMailDrafts';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { toggleId } from '@/lib/selection';
import { MAIL_INBOX, MAIL_READ_DWELL_MS } from '@/lib/workbench/mail';
import type { ComposerTarget } from '@/lib/workbench/mail-compose';
import { toolPath } from '@/lib/workbench/tools';
import type { MailMessage, MailSummary } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

export interface MailAddress {
  folder: string;
  openId: string | null;
  folderHref: (folderId: string) => string;
  messageHref: (message: MailSummary) => string;
  openMessage: (message: MailSummary) => void;
  closeMessage: () => void;
  pickFolder: (folderId: string) => void;
}

export function useMailAddress(lng: Language): MailAddress {
  const router = useRouter();
  const params = useSearchParams();
  const folder = params.get('folder') ?? MAIL_INBOX;
  const openId = params.get('id');

  const hrefOf = useCallback(
    (query: Record<string, string>) => {
      const encoded = new URLSearchParams(query).toString();
      return `${buildLocalizedPath(toolPath('mail'), lng)}${encoded ? `?${encoded}` : ''}`;
    },
    [lng]
  );
  const folderQuery = useMemo(
    (): Record<string, string> => (folder === MAIL_INBOX ? {} : { folder }),
    [folder]
  );
  const folderHref = useCallback(
    (id: string) => hrefOf(id === MAIL_INBOX ? {} : { folder: id }),
    [hrefOf]
  );
  const messageHref = useCallback(
    (message: MailSummary) => hrefOf({ ...folderQuery, id: message.id }),
    [folderQuery, hrefOf]
  );
  const openMessage = useCallback(
    (message: MailSummary) => router.push(messageHref(message), { scroll: false }),
    [messageHref, router]
  );
  const closeMessage = useCallback(
    () => router.replace(hrefOf(folderQuery), { scroll: false }),
    [folderQuery, hrefOf, router]
  );
  const pickFolder = useCallback(
    (id: string) => router.replace(folderHref(id), { scroll: false }),
    [folderHref, router]
  );
  return { folder, openId, folderHref, messageHref, openMessage, closeMessage, pickFolder };
}

export interface MailSelection {
  selected: ReadonlySet<string>;
  select: (ids: ReadonlySet<string>) => void;
  toggle: (id: string) => void;
}

/** @param listingKey - The listing the selection belongs to (its params, serialised). */
export function useMailSelection(listingKey: string): MailSelection {
  const [selection, setSelection] = useState<{ key: string; ids: ReadonlySet<string> }>({
    key: '',
    ids: new Set(),
  });
  const selected = useMemo(
    () => (selection.key === listingKey ? selection.ids : new Set<string>()),
    [listingKey, selection]
  );
  const select = useCallback(
    (ids: ReadonlySet<string>) => setSelection({ key: listingKey, ids }),
    [listingKey]
  );
  const toggle = useCallback((id: string) => select(toggleId(selected, id)), [select, selected]);
  return { selected, select, toggle };
}

export interface ComposerSlot {
  /** The open composer: a new id per opening, so a new composer and a new key. */
  composer: { id: number; target: ComposerTarget } | null;
  compose: (target: ComposerTarget) => void;
  close: () => void;
}

export function useComposerSlot(): ComposerSlot {
  const [composer, setComposer] = useState<ComposerSlot['composer']>(null);
  const openings = useRef(0);
  const compose = useCallback((target: ComposerTarget) => {
    openings.current += 1;
    setComposer({ id: openings.current, target });
  }, []);
  const close = useCallback(() => setComposer(null), []);
  return { composer, compose, close };
}

/**
 * Marks the open message read once it has been open for a look, never at a
 * glance — ONCE per opening: the person's own « Mark as unread » (or a glance
 * that marked it read by hand) is never overridden by a second look.
 */
export function useReadAfterLook(
  open: WorkbenchItemState<MailMessage>,
  markRead: () => Promise<void>
): void {
  const mark = useEffectEvent(() => void markRead());
  // The message the look was already given to (an external system's memory, not render state).
  const looked = useRef<string | null>(null);
  const unreadShown = open.item && !open.item.is_read ? open.item.id : null;
  const shownId = open.item?.id ?? null;
  // Nothing shown (closed, or another message loading): the next opening is a new look.
  useEffect(() => {
    if (shownId === null) looked.current = null;
  }, [shownId]);
  useEffect(() => {
    if (unreadShown === null || looked.current === unreadShown) return;
    looked.current = unreadShown;
    const timer = window.setTimeout(() => mark(), MAIL_READ_DWELL_MS);
    return () => window.clearTimeout(timer);
  }, [unreadShown]);
}

export interface DraftActs {
  opening: string | null;
  trashing: ReadonlySet<string>;
  openDraft: (id: string) => Promise<void>;
  trashDraft: (id: string) => Promise<void>;
}

export function useDraftActs(
  lng: Language,
  drafts: WorkbenchMailDrafts,
  compose: (target: ComposerTarget) => void,
  tell: (error: unknown) => void
): DraftActs {
  const { t } = useTranslation(lng);
  const [opening, setOpening] = useState<string | null>(null);
  const [trashing, setTrashing] = useState<ReadonlySet<string>>(new Set());
  const { read, trash } = drafts;

  const openDraft = useCallback(
    async (id: string) => {
      if (opening !== null) return;
      setOpening(id);
      try {
        compose({ kind: 'draft', draft: await read(id) });
      } catch (error: unknown) {
        tell(error);
      } finally {
        setOpening(null);
      }
    },
    [compose, opening, read, tell]
  );

  const trashDraft = useCallback(
    async (id: string) => {
      setTrashing(previous => toggleId(previous, id));
      try {
        const outcome = await trash([id]);
        if (outcome.failed.length > 0) toast.error(t('workbench.mail.none_done', { count: 1 }));
      } catch (error: unknown) {
        tell(error);
      } finally {
        setTrashing(previous => {
          const next = new Set(previous);
          next.delete(id);
          return next;
        });
      }
    },
    [t, tell, trash]
  );

  return { opening, trashing, openDraft, trashDraft };
}
