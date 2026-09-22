'use client';

/**
 * useEyesChatWiring — feeds the eyes' per-turn signals from the chat page.
 *
 * Kept out of ChatPage on purpose (its render function sits under the
 * shrink-only complexity ratchet). The hook:
 *  - marks a new turn on the idle→sending transition (per-turn signals reset)
 *  - resolves the post-response reaction when a turn completes: the register
 *    the answering model declared for that answer (ADR-253) when it arrived,
 *    the same register inferred from the answer's shape when it did not
 *  - hands the page two stable recorders for typing and notifications
 *
 * Messages are read through a ref: they change on every streamed token, and
 * the reaction only needs them at the completion instant.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';

import { REGISTER_EXPRESSIONS, inferToneFromContent, toneAmplitude } from '@/components/eyes/tone';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import type { Message } from '@/types/chat';
import type { ChatState } from '@/types/chat-state';

export interface EyesChatWiring {
  /** Call from the chat-input change handler (records typing activity). */
  onTyping: (message: string) => void;
  /** Pass as `onNotification` to useNotifications (records the ping). */
  onNotification: () => void;
}

/** Resolve and store the reaction for the message that just completed. */
function reactToCompletedTurn(messages: Message[], previousAnswer: string | null): void {
  const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
  if (!lastAssistant || lastAssistant.id === previousAnswer) return;
  if (useEyesSignalsStore.getState().completedAnswerId !== lastAssistant.id) return;
  if (lastAssistant.metadata?.interrupted || lastAssistant.metadata?.hitl_question) return;
  if (!lastAssistant.content?.trim()) return;
  const source = {
    content: lastAssistant.content ?? '',
    isError: lastAssistant.metadata?.type === 'error',
  };
  // ONE path, ONE vocabulary. The register the model declared is the better
  // signal — it knows what it chose — but it only arrives on a minority of
  // turns (measured: the in-band tag and the months-old psyche tag fired on
  // exactly the same 2 of 16 real turns), so the answer's own shape supplies
  // one when it does not. Both produce the same annotation, so the face is
  // computed the same way either way.
  //
  // The psyche is NOT consulted: it models a trait, and an argmax over a
  // near-constant vector is a constant — measured over fourteen consecutive
  // turns, it named the same emotion on thirteen.
  const tone = source.isError
    ? inferToneFromContent(source)
    : (useEyesSignalsStore.getState().pendingTone ?? inferToneFromContent(source));
  useEyesSignalsStore
    .getState()
    .setReaction(REGISTER_EXPRESSIONS[tone.register], toneAmplitude(tone), tone.accent);
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
  const previousAnswerRef = useRef<string | null>(null);
  const reactedId = useRef<string | null>(null);
  const completedId = useEyesSignalsStore(state => state.completedAnswerId);
  useEffect(() => () => useEyesSignalsStore.getState().reset(), []);

  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = chatStatus;
    if (chatStatus === prev) return;
    if (chatStatus === 'error') {
      useEyesSignalsStore.getState().endTurn();
      return;
    }
    if (chatStatus === 'sending') {
      previousAnswerRef.current =
        messagesRef.current.findLast(m => m.role === 'assistant')?.id ?? null;
      useEyesSignalsStore.getState().beginTurn();
      return;
    }
    // Only a LIVE completion reacts — history hydration (SET_MESSAGES) never
    // transitions from an in-flight status, so reloads stay expressionless.
    if (chatStatus === 'idle' && (prev === 'streaming' || prev === 'sending')) {
      if (!useEyesSignalsStore.getState().completedAnswerId)
        useEyesSignalsStore.getState().endTurn();
    }
  }, [chatStatus]);

  // Completion evidence survives React batching: even token + done in one
  // network read must react once, with the delivered message's own tone.
  useEffect(() => {
    if (chatStatus !== 'idle' || !completedId || reactedId.current === completedId) return;
    if (messages.findLast(message => message.role === 'assistant')?.id !== completedId) return;
    reactToCompletedTurn(messages, previousAnswerRef.current);
    reactedId.current = completedId;
    useEyesSignalsStore.getState().endTurn();
  }, [chatStatus, completedId, messages]);

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
