'use client';

/**
 * useInputDraft — per-user persistence of the chat input draft (UXR Lot 2, A7).
 *
 * The typed text survives refresh/navigation via a debounced localStorage save
 * keyed by user id (`lia.chatDraft.{userId}`). Rules:
 *
 * - empty/whitespace saves clear the key IMMEDIATELY and cancel any pending
 *   write — a refresh right after send must never resurrect the sent text;
 * - non-empty saves are debounced and clamped at `CHAT_INPUT_MAX_LENGTH`
 *   (mirror of the backend message cap);
 * - a pending write is flushed on unmount so navigation inside the debounce
 *   window never loses the last keystrokes;
 * - every storage access is try/catch-guarded — in private mode the draft
 *   simply does not survive;
 * - logout purges the key via `clearInputDraft` (called by the auth provider);
 * - future aparté mode (C2) must pass `enabled: false` — ephemeral contexts
 *   never persist.
 *
 * Multi-tab: last write wins; the draft is read once at mount (the dashboard
 * layout mounts the chat page only after the user is resolved, so `userId` is
 * stable for the hook's lifetime). Drafts are user content, never session
 * material — the BFF auth invariant is untouched.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';

import { CHAT_DRAFT_STORAGE_KEY_PREFIX, CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';

/** Debounce window between keystrokes and the localStorage write. */
const DRAFT_SAVE_DEBOUNCE_MS = 500;

function draftStorageKey(userId: string): string {
  return `${CHAT_DRAFT_STORAGE_KEY_PREFIX}${userId}`;
}

/** Remove a user's stored draft — logout path and explicit clears. */
export function clearInputDraft(userId: string): void {
  try {
    window.localStorage.removeItem(draftStorageKey(userId));
  } catch {
    // Storage unavailable (private mode) — nothing to purge.
  }
}

function readStoredDraft(userId: string): string | undefined {
  try {
    return window.localStorage.getItem(draftStorageKey(userId)) ?? undefined;
  } catch {
    return undefined;
  }
}

function writeStoredDraft(userId: string, value: string): void {
  try {
    window.localStorage.setItem(draftStorageKey(userId), value);
  } catch {
    // Storage unavailable or full — the draft simply does not survive.
  }
}

export interface UseInputDraftReturn {
  /** Draft read once at mount — feeds ChatInput's `initialMessage`. */
  initialDraft: string | undefined;
  /** Debounced persist; empty/whitespace clears immediately. */
  saveDraft: (value: string) => void;
}

export function useInputDraft(
  // The nullable user object (not a bare id): the null-branch lives HERE, in a
  // tiny function, instead of adding a branch to the page render hotspot
  // (frontend CC ratchet discipline).
  user: { id: string } | null | undefined,
  enabled = true
): UseInputDraftReturn {
  const userId = user?.id;
  const active = enabled && !!userId;

  const initialDraft = useMemo(
    () => (active && userId ? readStoredDraft(userId) : undefined),
    [active, userId]
  );

  const timerRef = useRef<number | null>(null);
  const pendingRef = useRef<string | null>(null);

  const saveDraft = useCallback(
    (value: string) => {
      if (!active || !userId) return;
      if (value.trim() === '') {
        if (timerRef.current !== null) {
          window.clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        pendingRef.current = null;
        clearInputDraft(userId);
        return;
      }
      pendingRef.current = value.slice(0, CHAT_INPUT_MAX_LENGTH);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        if (pendingRef.current !== null) {
          writeStoredDraft(userId, pendingRef.current);
          pendingRef.current = null;
        }
      }, DRAFT_SAVE_DEBOUNCE_MS);
    },
    [active, userId]
  );

  // Flush a pending write on unmount — navigating away inside the debounce
  // window must not lose the last keystrokes.
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (active && userId && pendingRef.current !== null) {
        writeStoredDraft(userId, pendingRef.current);
        pendingRef.current = null;
      }
    };
  }, [active, userId]);

  return { initialDraft, saveDraft };
}
