'use client';

/**
 * useEyesChatWiring — feeds the eyes' per-turn signals from the chat page.
 *
 * Kept out of ChatPage on purpose (its render function sits under the
 * shrink-only complexity ratchet). The hook:
 *  - marks a new turn on the idle→sending transition (per-turn signals reset)
 *  - resolves the post-response reaction when a turn completes: the per-turn
 *    psyche self-report from the done snapshot first, the language-neutral
 *    content heuristic when the snapshot is missing (race or psyche disabled)
 *  - hands the page two stable recorders for typing and notifications
 *
 * Messages are read through a ref: they change on every streamed token, and
 * the reaction only needs them at the completion instant.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';

import { deriveReaction } from '@/components/eyes/expression-engine';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import type { Message } from '@/types/chat';
import type { ChatState } from '@/types/chat-state';
import type { PsycheStateSummary } from '@/types/psyche';

export interface EyesChatWiring {
  /** Call from the chat-input change handler (records typing activity). */
  onTyping: (message: string) => void;
  /** Pass as `onNotification` to useNotifications (records the ping). */
  onNotification: () => void;
}

/** Emotions list from a done psyche snapshot (v2 list, v1 single fallback). */
function snapshotEmotions(
  snapshot: PsycheStateSummary | undefined
): Array<{ name: string; intensity: number }> | null {
  if (!snapshot) return null;
  if (snapshot.active_emotions?.length) return snapshot.active_emotions;
  if (snapshot.active_emotion) {
    return [{ name: snapshot.active_emotion, intensity: snapshot.emotion_intensity }];
  }
  return null;
}

/** Resolve and store the reaction for the message that just completed. */
function reactToCompletedTurn(messages: Message[]): void {
  const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
  if (!lastAssistant) return;
  const snapshot = lastAssistant.metadata?.psyche_state as PsycheStateSummary | undefined;
  const reaction = deriveReaction({
    psycheEmotions: snapshotEmotions(snapshot),
    content: lastAssistant.content ?? '',
    isError: lastAssistant.metadata?.type === 'error',
    hasArtifacts: Boolean(
      lastAssistant.generatedImages?.length || lastAssistant.generatedDocuments?.length
    ),
  });
  if (reaction) useEyesSignalsStore.getState().setReaction(reaction);
}

export function useEyesChatWiring(
  chatStatus: ChatState['status'],
  messages: Message[]
): EyesChatWiring {
  const messagesRef = useRef(messages);
  // Declared BEFORE the transition effect below: effects run in order, so the
  // ref is up to date when the completion transition reads it.
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const prevStatusRef = useRef(chatStatus);

  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = chatStatus;
    if (chatStatus === prev) return;
    if (chatStatus === 'sending') {
      useEyesSignalsStore.getState().beginTurn();
      return;
    }
    // Only a LIVE completion reacts — history hydration (SET_MESSAGES) never
    // transitions from an in-flight status, so reloads stay expressionless.
    if (chatStatus === 'idle' && (prev === 'streaming' || prev === 'sending')) {
      reactToCompletedTurn(messagesRef.current);
    }
  }, [chatStatus]);

  const onTyping = useCallback((message: string) => {
    if (message.length > 0) useEyesSignalsStore.getState().recordTyping();
  }, []);

  const onNotification = useCallback(() => {
    useEyesSignalsStore.getState().recordNotification();
  }, []);

  // Stable object identity: the page folds this into other useCallback deps
  // (handleMessageChange) — a fresh object every render would churn those
  // identities and ripple re-renders into ChatInput.
  return useMemo(() => ({ onTyping, onNotification }), [onTyping, onNotification]);
}
