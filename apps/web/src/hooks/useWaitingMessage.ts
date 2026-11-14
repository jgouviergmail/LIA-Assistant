'use client';

/**
 * useWaitingMessage — the discussion's message that waits for its turn (ADR-384).
 *
 * The server keeps the words written while LIA works; this hook reads the
 * selected discussion's one and writes through its five doors (keep, edit,
 * withdraw, send now, join the answer being written — ADR-385). What is shown
 * changes only from a server answer: a refused request leaves the message on
 * screen as it was, and rethrows so the caller can say why.
 */

import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { conversationParams, conversationQuery } from '@/lib/conversation-selection';
import type {
  WaitingMessage,
  WaitingQueueResponse,
  WaitingSendResponse,
} from '@/lib/waiting-message';
import type { ConversationSelection } from '@/types/conversation';

const ENDPOINT = '/agents/chat/waiting';
const COMPONENT = 'useWaitingMessage';

/** The browser's display hints the turn will start with; never its location. */
export interface WaitingRendering {
  lia_gender?: 'male' | 'female';
  viewport_width?: number;
}

export interface QueueOptions {
  /** The run the words were written behind, when the page saw one running. */
  behindStreamId: string | null;
  rendering?: WaitingRendering;
}

export interface UseWaitingMessageReturn {
  /** The discussion's waiting message, or null. */
  message: WaitingMessage | null;
  /** Read it again (after a turn ended, on a thread signal). */
  refresh: () => Promise<void>;
  /** Keep words with the discussion; on a free account they may leave at once. */
  queue: (text: string, options: QueueOptions) => Promise<WaitingQueueResponse | undefined>;
  /** Replace the words of the version on screen. */
  edit: (text: string) => Promise<WaitingMessage | undefined>;
  /** Withdraw it before it leaves. */
  withdraw: () => Promise<void>;
  /** « Send now »: stop this discussion's answer, then send. */
  sendNow: () => Promise<WaitingSendResponse | undefined>;
  /** Add it to the answer being written, as the version on screen (ADR-385). */
  join: () => Promise<WaitingMessage | undefined>;
  /** A request is on its way. */
  pending: boolean;
}

export function useWaitingMessage(
  selection: ConversationSelection | undefined,
  enabled: boolean
): UseWaitingMessageReturn {
  const params = useMemo(() => conversationParams(selection), [selection]);
  const url = `${ENDPOINT}${conversationQuery(selection)}`;
  const query = useApiQuery<WaitingMessage | null>(ENDPOINT, {
    componentName: COMPONENT,
    params,
    enabled,
  });
  const keep = useApiMutation<Record<string, unknown>, WaitingQueueResponse>({
    method: 'POST',
    componentName: COMPONENT,
  });
  const change = useApiMutation<{ message: string; version: number }, WaitingMessage>({
    method: 'PUT',
    componentName: COMPONENT,
  });
  const remove = useApiMutation<undefined, void>({ method: 'DELETE', componentName: COMPONENT });
  const send = useApiMutation<undefined, WaitingSendResponse>({
    method: 'POST',
    componentName: COMPONENT,
  });
  const note = useApiMutation<{ version: number }, WaitingMessage>({
    method: 'POST',
    componentName: COMPONENT,
  });
  const { setData, refetch } = query;
  const message = query.data ?? null;

  const queue = useCallback(
    async (text: string, options: QueueOptions) => {
      const body: Record<string, unknown> = { message: text };
      if (options.behindStreamId) body.behind_stream_id = options.behindStreamId;
      if (options.rendering) body.rendering = options.rendering;
      const response = await keep.mutate(url, body);
      if (response) setData(response.waiting);
      return response;
    },
    [keep, url, setData]
  );

  const edit = useCallback(
    async (text: string) => {
      if (message === null) return undefined;
      const edited = await change.mutate(url, { message: text, version: message.version });
      if (edited) setData(edited);
      return edited;
    },
    [change, url, message, setData]
  );

  const withdraw = useCallback(async () => {
    await remove.mutate(url);
    setData(null);
  }, [remove, url, setData]);

  const sendNow = useCallback(async () => {
    const response = await send.mutate(`${ENDPOINT}/send${conversationQuery(selection)}`);
    await refetch();
    return response;
  }, [send, selection, refetch]);

  const join = useCallback(async () => {
    if (message === null) return undefined;
    const joined = await note.mutate(`${ENDPOINT}/join${conversationQuery(selection)}`, {
      version: message.version,
    });
    if (joined) setData(joined);
    return joined;
  }, [note, selection, message, setData]);

  return {
    message,
    refresh: refetch,
    queue,
    edit,
    withdraw,
    sendNow,
    join,
    pending: keep.loading || change.loading || remove.loading || send.loading || note.loading,
  };
}
