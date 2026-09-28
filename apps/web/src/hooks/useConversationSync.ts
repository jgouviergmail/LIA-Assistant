'use client';

/**
 * Wires the chat's sync controller (ADR-320) — see `lib/chat-sync.ts`.
 *
 * The controller is created in an effect, never during render: React's
 * StrictMode mounts, unmounts and mounts again in development, and a
 * controller created once and disposed by the first unmount would leave the
 * second mount with a dead one. The options are read through a ref so the
 * controller never needs to be rebuilt when they change.
 *
 * Two asks come from here on their own — the tab back in the foreground, the
 * device back online — because both are moments when a signal may have been
 * missed. The chat page adds the others (a signal, a notification, a stream
 * reconnected).
 */

import { useCallback, useEffect, useRef } from 'react';

import { ChatSyncController, type SyncReason } from '@/lib/chat-sync';
import type { Message } from '@/types/chat';

/**
 * Whether the reader is in the middle of a gesture a re-render could disturb:
 * text selected in the page, or a menu open.
 *
 * @param doc - The document to look at.
 * @returns True while the gesture lasts.
 */
export function readerBusy(doc: Document = document): boolean {
  const selection = doc.getSelection();
  if (selection !== null && !selection.isCollapsed && selection.toString().trim() !== '') {
    return true;
  }
  return doc.querySelector('[role="menu"][data-state="open"]') !== null;
}

export interface UseConversationSyncOptions<Page extends { messages: Message[] }> {
  /** Whether syncing makes sense at all (signed in, API reachable). */
  enabled: boolean;
  /** Whether the thread must not be touched now (streaming, past page, paginating). */
  blocked: boolean;
  /** The thread on screen. */
  messages: Message[];
  /** The newest page; throws on a transport failure. */
  readNewestPage: () => Promise<Page>;
  /** Merge a page into the thread. */
  mergeServerPage: (messages: Message[]) => void;
  /** The page lay beyond the thread: restart pagination from it. */
  onPageReplaced: (page: Page) => void;
  /** The server emptied the conversation. */
  onReset: () => void;
}

export interface UseConversationSyncReturn {
  /** Ask for the newest page to be merged (coalesced, deferred while busy). */
  requestSync: (reason: SyncReason) => void;
  /** The server announced a reset: empty the thread once it is free. */
  requestReset: () => void;
}

export function useConversationSync<Page extends { messages: Message[] }>(
  options: UseConversationSyncOptions<Page>
): UseConversationSyncReturn {
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });

  const controllerRef = useRef<ChatSyncController<Page> | null>(null);
  useEffect(() => {
    const controller = new ChatSyncController<Page>({
      enabled: () => latest.current.enabled,
      blocked: () => latest.current.blocked,
      readerBusy: () => readerBusy(),
      messages: () => latest.current.messages,
      readNewestPage: () => latest.current.readNewestPage(),
      mergeServerPage: messages => latest.current.mergeServerPage(messages),
      onPageReplaced: page => latest.current.onPageReplaced(page),
      onReset: () => latest.current.onReset(),
      setTimer: (callback, ms) => setTimeout(callback, ms),
      clearTimer: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
    });
    controllerRef.current = controller;
    return () => {
      controller.dispose();
      controllerRef.current = null;
    };
  }, []);

  const requestSync = useCallback((reason: SyncReason) => {
    controllerRef.current?.request(reason);
  }, []);
  const requestReset = useCallback(() => {
    controllerRef.current?.requestReset();
  }, []);

  // What was asked while the thread was busy runs once it is free.
  const { enabled, blocked } = options;
  useEffect(() => {
    if (enabled && !blocked) controllerRef.current?.resume();
  }, [enabled, blocked]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'visible') requestSync('visible');
    };
    const onOnline = () => requestSync('online');
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('online', onOnline);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('online', onOnline);
    };
  }, [requestSync]);

  return { requestSync, requestReset };
}
