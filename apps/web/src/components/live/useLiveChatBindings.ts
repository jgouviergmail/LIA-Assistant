'use client';

/**
 * How the live session talks to the chat (ADR-299, spec A3): the chat's own
 * `sendMessage`, and a read of the LAST answer once the stream ended. Refs,
 * because the messages change on every token and the bridge needs them only
 * at the instant the stream resolves — reading them through a closure would
 * hand the bridge the thread as it was when the session started.
 *
 * A pending HITL question IS the answer: the question is the last assistant
 * row (the card's text), and the voice reads it to the person so they can
 * answer aloud through the next delegation.
 *
 * `readAnswer` resolves AFTER a commit: the chat's `sendMessage` resolves the
 * instant the stream ends, one render BEFORE the thread holds the final
 * tokens (measured in the browser 2026-09-18: the voice was handed an empty
 * answer). A reader therefore queues itself, forces a render, and is served
 * by the effect that runs once React committed — every pending dispatch is
 * folded into that same render, so the refs it reads are the stream's last
 * word. No timer, no frame guess.
 */
import { useEffect, useMemo, useReducer, useRef } from 'react';

import type { LiveChatBindings, LiveSpokenMeta } from '@/lib/live/session-controller';
import { hitlAwaitsUser } from '@/lib/chat-surfaces';
import type { Message } from '@/types/chat';
import type { HitlCardStatus } from '@/types/hitl';

export interface LiveChatSource {
  messages: Message[];
  hitl: { status: HitlCardStatus };
  /** The chat's `sendMessage`, with the live meta as its LAST parameter. */
  sendMessage: (
    content: string,
    attachmentIds?: string[],
    attachmentsMeta?: undefined,
    sttMeta?: undefined,
    hitlDecision?: undefined,
    directive?: undefined,
    liveMeta?: LiveSpokenMeta
  ) => Promise<void>;
  appendMessage: (message: Message) => void;
  /** The chat's Stop (ADR-117): cancels the running turn, server-side first. */
  stopGeneration: () => Promise<void>;
}

/** The register the answering model declared for a row (ADR-253), or null. */
function registerOf(message: Message | undefined): string | null {
  const expressivity = message?.metadata?.expressivity;
  if (!expressivity || typeof expressivity !== 'object') return null;
  const register = (expressivity as { register?: unknown }).register;
  return typeof register === 'string' && register ? register : null;
}

/**
 * The last assistant row's text, whether it is a question waiting for the
 * person, and the register it was said in (the voice's delivery note).
 */
export function readLastAnswer(messages: readonly Message[], hitlStatus: HitlCardStatus): Answer {
  let last: Message | undefined;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') {
      last = messages[i];
      break;
    }
  }
  const text = last?.content ?? '';
  const register = registerOf(last);
  if (hitlAwaitsUser(hitlStatus)) return { text: '', pendingQuestion: text, register };
  return { text, pendingQuestion: null, register };
}

type Answer = { text: string; pendingQuestion: string | null; register: string | null };

export function useLiveChatBindings(chat: LiveChatSource): LiveChatBindings {
  const messagesRef = useRef(chat.messages);
  const hitlRef = useRef(chat.hitl);
  const readersRef = useRef<Array<(answer: Answer) => void>>([]);
  const [, forceRender] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    messagesRef.current = chat.messages;
    hitlRef.current = chat.hitl;
    if (readersRef.current.length === 0) return;
    const answer = readLastAnswer(chat.messages, chat.hitl.status);
    const readers = readersRef.current;
    readersRef.current = [];
    for (const resolve of readers) resolve(answer);
  });
  // A reader queued right before the page unmounts would wait for a commit
  // that never comes: serve it the last thread the page held.
  useEffect(
    () => () => {
      const readers = readersRef.current;
      readersRef.current = [];
      if (readers.length === 0) return;
      const answer = readLastAnswer(messagesRef.current, hitlRef.current.status);
      for (const resolve of readers) resolve(answer);
    },
    []
  );
  const { sendMessage, appendMessage, stopGeneration } = chat;
  return useMemo(
    () => ({
      sendMessage: (content, meta) =>
        sendMessage(content, undefined, undefined, undefined, undefined, undefined, meta),
      stop: stopGeneration,
      appendMessage,
      readAnswer: () =>
        new Promise<Answer>(resolve => {
          readersRef.current.push(resolve);
          forceRender();
        }),
    }),
    [sendMessage, appendMessage, stopGeneration]
  );
}
