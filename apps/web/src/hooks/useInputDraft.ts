'use client';

/**
 * useInputDraft — per-account and per-discussion composer persistence.
 *
 * The typed text survives refresh/navigation via a debounced localStorage save
 * keyed by account and discussion. Main has a stable role key before its first message.
 *
 * - empty/whitespace saves clear the key IMMEDIATELY and cancel any pending
 *   write — a refresh right after send must never resurrect the sent text;
 * - non-empty saves are debounced and clamped at `CHAT_INPUT_MAX_LENGTH`
 *   (mirror of the backend message cap);
 * - a pending write is flushed on unmount so navigation inside the debounce
 *   window never loses the last keystrokes;
 * - every storage access is try/catch-guarded — in private mode the draft
 *   simply does not survive;
 * - logout purges every account draft and invalidates pending writes;
 * - future aparté mode (C2) must pass `enabled: false` — ephemeral contexts
 *   never persist.
 *
 * Multi-tab: last write wins per discussion; the draft is read on mount or
 * target change, without replacing text someone is typing. Drafts are user content, never session
 * material — the BFF auth invariant is untouched.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';

import { CHAT_DRAFT_STORAGE_KEY_PREFIX, CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';
import { decodeCompositionDraft, encodeCompositionDraft } from '@/lib/card-composition-draft';
import type { CardCompositionDraft } from '@/types/card-actions';

/** Debounce window between keystrokes and the localStorage write. */
const DRAFT_SAVE_DEBOUNCE_MS = 500;

interface DraftDiscussion {
  id: string;
  kind: 'main' | 'secondary';
}

const ownerEpochs = new Map<string, number>();
const discussionEpochs = new Map<string, number>();

function draftStorageKey(userId: string, discussion?: DraftDiscussion): string {
  return `${CHAT_DRAFT_STORAGE_KEY_PREFIX}${userId}.${discussion?.kind === 'secondary' ? discussion.id : 'main'}`;
}

function draftGeneration(userId: string | undefined, key: string | undefined): string {
  return `${userId ? (ownerEpochs.get(userId) ?? 0) : 0}:${key ? (discussionEpochs.get(key) ?? 0) : 0}`;
}

/** A committed reset retires only this draft, including a write still waiting to flush. */
export function clearDiscussionDraft(userId: string, discussion: DraftDiscussion): void {
  if (discussion.kind === 'main') migrateMainDraft(userId);
  const key = draftStorageKey(userId, discussion);
  discussionEpochs.set(key, (discussionEpochs.get(key) ?? 0) + 1);
  writeStoredDraft(key, '');
}

/** Recover a deleted annex's text without opening a composer or transferring its action. */
export function readDiscussionDraft(userId: string, id: string): string | undefined {
  return decodeCompositionDraft(readStoredDraft(draftStorageKey(userId, { id, kind: 'secondary' })))
    .text;
}

/** Remove a user's stored draft — logout path and explicit clears. */
export function clearInputDraft(userId: string): void {
  ownerEpochs.set(userId, (ownerEpochs.get(userId) ?? 0) + 1);
  try {
    const legacy = `${CHAT_DRAFT_STORAGE_KEY_PREFIX}${userId}`;
    for (const key of Object.keys(window.localStorage)) {
      if (key === legacy || key.startsWith(`${legacy}.`)) window.localStorage.removeItem(key);
    }
  } catch {
    // Storage unavailable (private mode) — nothing to purge.
  }
}

function readStoredDraft(key: string): string | undefined {
  try {
    return window.localStorage.getItem(key) ?? undefined;
  } catch {
    return undefined;
  }
}

function writeStoredDraft(key: string, value: string): void {
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch {
    // Storage unavailable or full — the draft simply does not survive.
  }
}

/**
 * Leaves a text for the chat composer, which reads the draft when it opens: an
 * address would be logged by every server on the way, and a stored draft is not.
 * What the person had started stays, above it.
 *
 * @param userId - The account.
 * @param text - The words to find there; nothing is sent.
 */
export function seedInputDraft(userId: string, text: string): void {
  migrateMainDraft(userId);
  const key = draftStorageKey(userId);
  const { text: started } = decodeCompositionDraft(readStoredDraft(key));
  const draft = started?.trim() ? `${started}\n\n${text}` : text;
  writeStoredDraft(key, draft.slice(0, CHAT_INPUT_MAX_LENGTH));
}

/** Move the legacy draft only after storage accepted the new Main key. */
function migrateMainDraft(userId: string): void {
  try {
    const oldKey = `${CHAT_DRAFT_STORAGE_KEY_PREFIX}${userId}`;
    const key = draftStorageKey(userId);
    const legacy = window.localStorage.getItem(oldKey);
    if (legacy === null) return;
    if (window.localStorage.getItem(key) === null) window.localStorage.setItem(key, legacy);
    window.localStorage.removeItem(oldKey);
  } catch {
    // Preserve the old copy if storage refused the migration.
  }
}

export interface UseInputDraftReturn {
  /** Draft read once at mount — feeds ChatInput's `initialMessage`. */
  initialDraft: string | undefined;
  initialComposition?: CardCompositionDraft;
  /** Debounced persist; empty/whitespace clears immediately. */
  saveDraft: (value: string, composition?: CardCompositionDraft) => void;
}

/** True when the released text belongs to a read-only recovery view. */
export type RecoverReleasedDraft = (text: string | undefined) => boolean;

export function useInputDraft(
  // The nullable user object (not a bare id): the null-branch lives HERE, in a
  // tiny function, instead of adding a branch to the page render hotspot
  // (frontend CC ratchet discipline).
  user: { id: string } | null | undefined,
  enabled = true,
  discussion?: DraftDiscussion,
  recoverOnRelease?: RecoverReleasedDraft
): UseInputDraftReturn {
  const userId = user?.id;
  const active = enabled && !!userId;
  const key = userId ? draftStorageKey(userId, discussion) : undefined;
  const isMain = discussion?.kind !== 'secondary';
  const epoch = useMemo(() => draftGeneration(userId, key), [userId, key]);

  const initial = useMemo(
    () =>
      decodeCompositionDraft(
        active && key
          ? (readStoredDraft(key) ??
              (isMain ? readStoredDraft(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}${userId}`) : undefined))
          : undefined
      ),
    [active, key, isMain, userId]
  );

  useEffect(() => {
    if (active && userId && isMain) migrateMainDraft(userId);
  }, [active, userId, isMain]);

  const timerRef = useRef<number | null>(null);
  const editedDraft = useRef<string | null>(null);

  const saveDraft = useCallback(
    (value: string, composition?: CardCompositionDraft) => {
      if (!active || !userId || !key || epoch !== draftGeneration(userId, key)) return;
      if (value.trim() === '') {
        if (timerRef.current !== null) {
          window.clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        editedDraft.current = '';
        writeStoredDraft(key, '');
        return;
      }
      const draft = encodeCompositionDraft(value.slice(0, CHAT_INPUT_MAX_LENGTH), composition);
      editedDraft.current = draft;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        if (epoch === draftGeneration(userId, key)) writeStoredDraft(key, draft);
      }, DRAFT_SAVE_DEBOUNCE_MS);
    },
    [active, userId, key, epoch]
  );

  // Flush a pending write on unmount — navigating away inside the debounce
  // window must not lose the last keystrokes.
  useEffect(() => {
    return () => {
      const timer = timerRef.current;
      const draft = editedDraft.current;
      timerRef.current = null;
      editedDraft.current = null;
      if (timer !== null) window.clearTimeout(timer);
      if (!active || !userId || !key || epoch !== draftGeneration(userId, key)) return;
      // A deletion confirmed in another tab may have removed the shared copy.
      const recovered = recoverOnRelease?.(
        draft === null ? initial.text : decodeCompositionDraft(draft).text
      );
      if (!recovered && timer !== null && draft !== null) writeStoredDraft(key, draft);
    };
  }, [active, userId, key, epoch, initial.text, recoverOnRelease]);

  return { initialDraft: initial.text, initialComposition: initial.composition, saveDraft };
}
