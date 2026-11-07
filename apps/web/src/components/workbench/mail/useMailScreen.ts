'use client';

/**
 * The mail screen's small state machines (ADR-369, Task 4.7), each one job:
 *
 * - the ADDRESS: the open folder and message ride the query string — opening
 *   a message pushes, closing replaces, so « back » closes the reader;
 * - the COMPOSER slot: each opening mounts a new composer, hence a new key;
 * - the FIRST LOOK: a large screen opens on the inbox's newest message, which nobody asked for;
 * - the LOOK: an unread message the person opened, open for `MAIL_READ_DWELL_MS`, is marked read;
 * - the DRAFTS' row acts: one draft opened at a time, each trash answered;
 * - the IMAGES a message carries: read apart, once its layout names them;
 * - the FRESHNESS: a folder's figure growing means mail arrived, and its listing
 *   is read again without being asked;
 * - the CONVERSATION: read once the message landed, so the message never waits for it, and
 *   kept while the person walks it;
 * - the LINES: the listing as the list draws it, by this device's grouping.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { toast } from 'sonner';

import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { WorkbenchMailDrafts } from '@/hooks/useWorkbenchMailDrafts';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { toggleId } from '@/lib/selection';
import {
  MAIL_INBOX,
  MAIL_READ_DWELL_MS,
  cidsOf,
  conversationAnchor,
  mailLines,
  readMailGrouping,
  subscribeMailGrouping,
  type MailGrouping,
  type MailLine,
} from '@/lib/workbench/mail';
import type { ComposerTarget } from '@/lib/workbench/mail-compose';
import { toolPath } from '@/lib/workbench/tools';
import type {
  MailConversation,
  MailInlineImages,
  MailMessage,
  MailSummary,
  RereadOptions,
} from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

const INLINE_IMAGES_PATH = '/workbench/mail/message/images';
const CONVERSATION_PATH = '/workbench/mail/conversation';
const NO_ROWS: readonly MailSummary[] = [];

const flat = (): MailGrouping => 'flat';

export interface MailLines {
  lines: readonly MailLine[];
  /** This device's grouping. */
  grouping: MailGrouping;
}

/** @param rows - What is loaded, in the listing's order. */
export function useMailLines(rows: readonly MailSummary[]): MailLines {
  const grouping = useSyncExternalStore(subscribeMailGrouping, readMailGrouping, flat);
  const lines = useMemo(() => mailLines(rows, grouping === 'grouped'), [grouping, rows]);
  return { lines, grouping };
}

export interface ConversationState {
  /** Its messages, oldest first; none until read. */
  rows: readonly MailSummary[];
  /** It holds older messages than these. */
  truncated: boolean;
  /** It could not be read: the message stands alone, and says why. */
  failed: boolean;
  /** The person opened the list. */
  expanded: boolean;
  setExpanded: (expanded: boolean) => void;
  refresh: (options?: RereadOptions) => Promise<void>;
}

/**
 * @param reading - The reader is open.
 * @param message - The message on screen, once it landed.
 */
export function useConversation(
  reading: boolean,
  message: MailMessage | undefined
): ConversationState {
  const [anchor, setAnchor] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const read = useWorkbenchItem<MailConversation>(anchor ? CONVERSATION_PATH : null, {
    id: anchor ?? undefined,
  });
  const next = conversationAnchor(anchor, read.item?.items, reading, message?.id);
  if (next !== anchor) {
    setAnchor(next);
    setExpanded(false);
  }
  return {
    rows: read.item?.items ?? NO_ROWS,
    truncated: read.item?.truncated ?? false,
    failed: read.error !== null,
    expanded,
    setExpanded,
    refresh: read.refresh,
  };
}

export interface MailAddress {
  folder: string;
  openId: string | null;
  folderHref: (folderId: string) => string;
  messageHref: (message: MailSummary) => string;
  openMessage: (message: MailSummary) => void;
  /** Opens another message in the place of the open one (« back » skips it). */
  replaceMessage: (message: MailSummary) => void;
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
  const replaceMessage = useCallback(
    (message: MailSummary) => router.replace(messageHref(message), { scroll: false }),
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
  return {
    folder,
    openId,
    folderHref,
    messageHref,
    openMessage,
    replaceMessage,
    closeMessage,
    pickFolder,
  };
}

/**
 * What a large screen shows when the mailbox opens: the inbox's newest message, as a mail
 * application does. The person did not open it, so it rides no address and is never marked read;
 * a message arriving does not take its place. Whatever the person does with the reader then
 * (closing it, opening a message, leaving the inbox) lets go of it for the rest of the visit.
 *
 * @param address - What the person asked for.
 * @param rows - The inbox as it lists, the newest first; none while a search narrows it.
 * @param wide - The reader stands beside the list, which it would otherwise replace.
 * @returns The address the screen reads, what it shows by itself included.
 */
export function useFirstLook(
  address: MailAddress,
  rows: readonly MailSummary[],
  wide: boolean
): MailAddress {
  const atInbox = address.openId === null && address.folder === MAIL_INBOX;
  const [waiting, setWaiting] = useState(atInbox);
  const [firstId, setFirstId] = useState<string | null>(null);
  const newest = rows[0]?.id ?? null;
  if (waiting && !atInbox) setWaiting(false);
  if (waiting && firstId === null && newest !== null) setFirstId(newest);
  if (!waiting || !wide || !atInbox || firstId === null) return address;
  return { ...address, openId: firstId, closeMessage: () => setWaiting(false) };
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
 *
 * @param open - The open message.
 * @param markRead - Marks it read.
 * @param asked - The person opened it: what a screen shows by itself stays as it is.
 */
export function useReadAfterLook(
  open: WorkbenchItemState<MailMessage>,
  markRead: () => Promise<void>,
  asked: boolean
): void {
  const mark = useEffectEvent(() => void markRead());
  // The message the look was already given to (an external system's memory, not render state).
  const looked = useRef<string | null>(null);
  const unreadShown = asked && open.item && !open.item.is_read ? open.item.id : null;
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

const NO_CIDS: readonly string[] = [];

/**
 * @param messageId - The open message.
 * @param html - Its layout, once read.
 * @returns The images it carries, once read; nothing is asked where it names none.
 */
export function useInlineImages(
  messageId: string | null,
  html: string | null
): MailInlineImages | undefined {
  const cids = useMemo(() => (html ? cidsOf(html) : NO_CIDS), [html]);
  const params = useMemo(
    () => ({ message_id: messageId ?? undefined, cid: [...cids] }),
    [cids, messageId]
  );
  const read = useWorkbenchItem<MailInlineImages>(
    messageId && cids.length > 0 ? INLINE_IMAGES_PATH : null,
    params
  );
  if (read.error && !read.item) return { images: [], skipped: cids.length };
  return read.item;
}

/**
 * Reads the listing again when what it leaves unread grows: a message arrived. A figure
 * that falls is the person's own reading, and asks for nothing.
 *
 * @param folder - The listing.
 * @param counts - The figures, once read.
 * @param reread - Reads the listing again.
 */
export function useFreshListing(
  folder: string,
  counts: Readonly<Record<string, number>> | undefined,
  reread: () => void
): void {
  const figure = counts?.[folder];
  const seen = useRef<{ folder: string; figure: number | undefined }>({ folder, figure });
  const read = useEffectEvent(reread);
  useEffect(() => {
    const before = seen.current;
    seen.current = { folder, figure };
    if (before.folder !== folder || before.figure === undefined || figure === undefined) return;
    if (figure > before.figure) read();
  }, [folder, figure]);
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
