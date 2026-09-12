'use client';

/**
 * Which archived answers the person kept — ONE read for the whole chat (ADR-282).
 *
 * Every assistant bubble draws a bookmark toggle. Each bubble asking the API
 * for its own state would cost one request per answer on every open of the
 * conversation (the `ShareResponseMenu` lesson: 120 requests on twelve
 * answers), so the state is read ONCE here, as the map the API publishes
 * (`GET /bookmarks/state`, bounded by the account's cap), and every bubble
 * reads it from context.
 *
 * The toggle is optimistic: the icon fills at the click, and a refusal (the
 * cap, the operator's switch, a message the server does not know) rolls it
 * back and says why. Outside the provider the context is inert — a bubble
 * rendered in isolation (a test, an archived read-only view) shows no toggle.
 */

import * as React from 'react';

import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { Bookmark, BookmarkKeepRequest, BookmarkState } from '@/types/bookmarks';

export interface BookmarkStateValue {
  /** Whether the bubble may offer the toggle at all (deployment flag + provider). */
  enabled: boolean;
  /** The bookmark id attached to a message, or undefined when it is not kept. */
  bookmarkIdOf: (messageDbId: string) => string | undefined;
  /**
   * Keep or drop one message. Resolves to the new state; rejects with the
   * API error when the server refused, after rolling the icon back.
   */
  toggle: (messageDbId: string) => Promise<'kept' | 'removed'>;
}

const INERT: BookmarkStateValue = {
  enabled: false,
  bookmarkIdOf: () => undefined,
  toggle: () => Promise.reject(new Error('bookmarks are not available here')),
};

const BookmarkStateContext = React.createContext<BookmarkStateValue>(INERT);

export interface BookmarkStateProviderProps {
  /** The instance publishes `features.bookmarks_enabled`; false mounts nothing. */
  enabled: boolean;
  children: React.ReactNode;
}

/** A pending optimistic entry: the icon is filled, the row not yet confirmed. */
const PENDING = 'pending';

export function BookmarkStateProvider({ enabled, children }: BookmarkStateProviderProps) {
  const [attached, setAttached] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    apiClient
      .get<BookmarkState>('/bookmarks/state')
      .then(state => {
        // MERGED under what the person already did: a click confirmed while
        // this read was in flight is newer than the map the read returns, and
        // replacing would empty an icon the server has already filled.
        if (!cancelled) setAttached(previous => ({ ...(state.message_ids ?? {}), ...previous }));
      })
      .catch((error: unknown) => {
        // A failed read leaves every toggle empty rather than breaking the
        // chat: the person can still keep an answer, and the server answers
        // 200 for one already kept.
        logger.warn('bookmark_state_load_failed', {
          component: 'BookmarkStateProvider',
          error: error instanceof Error ? error.message : String(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const bookmarkIdOf = React.useCallback(
    (messageDbId: string) => attached[messageDbId],
    [attached]
  );

  const toggle = React.useCallback(
    async (messageDbId: string): Promise<'kept' | 'removed'> => {
      const current = attached[messageDbId];
      // A second click while the first is in flight would delete a row that
      // does not exist yet and roll the icon back on the 404: the click that
      // is pending answers for both.
      if (current === PENDING) return 'kept';
      if (current === undefined) {
        setAttached(previous => ({ ...previous, [messageDbId]: PENDING }));
        try {
          const body: BookmarkKeepRequest = { message_id: messageDbId };
          const kept = await apiClient.post<Bookmark>('/bookmarks', body);
          setAttached(previous => ({ ...previous, [messageDbId]: kept.id }));
          return 'kept';
        } catch (error) {
          setAttached(previous => {
            const next = { ...previous };
            delete next[messageDbId];
            return next;
          });
          throw error;
        }
      }
      setAttached(previous => {
        const next = { ...previous };
        delete next[messageDbId];
        return next;
      });
      try {
        await apiClient.delete<undefined>(`/bookmarks/by-message/${messageDbId}`);
        return 'removed';
      } catch (error) {
        setAttached(previous => ({ ...previous, [messageDbId]: current }));
        throw error;
      }
    },
    [attached]
  );

  const value = React.useMemo<BookmarkStateValue>(
    () => ({ enabled, bookmarkIdOf, toggle }),
    [enabled, bookmarkIdOf, toggle]
  );

  return <BookmarkStateContext.Provider value={value}>{children}</BookmarkStateContext.Provider>;
}

/** The bookmark state of the surrounding chat; inert outside a provider. */
export function useBookmarkState(): BookmarkStateValue {
  return React.useContext(BookmarkStateContext);
}
