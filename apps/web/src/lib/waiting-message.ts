/**
 * Words written while LIA works wait for their turn, kept by the server (ADR-384),
 * or join the answer being written as a note (ADR-385).
 *
 * Pure decisions only: what the composer does with a send, which sentence
 * states where a waiting message stands, and which actions it offers. The
 * server owns the state; these read it.
 */

/** Where a waiting message stands, as the server says it. */
export type WaitingStatus = 'waiting' | 'held' | 'departing' | 'joining';

/** One discussion's waiting message (`GET /agents/chat/waiting`). */
export interface WaitingMessage {
  conversation_id: string;
  conversation_revision: number;
  content: string;
  status: WaitingStatus;
  version: number;
  send_requested: boolean;
  stream_id: string | null;
  /** The answer being written in this discussion takes it as a note now. */
  can_join: boolean;
  created_at: string;
  updated_at: string;
}

/** What became of words just written (`POST /agents/chat/waiting`). */
export interface WaitingQueueResponse {
  waiting: WaitingMessage | null;
  departed: boolean;
  stream_id: string | null;
}

/** What « Send now » set in motion (`POST /agents/chat/waiting/send`). */
export interface WaitingSendResponse {
  departed: boolean;
  stopping: boolean;
  stream_id: string | null;
}

/** What a send carries beyond its text: anything here keeps the live request. */
export interface SendExtras {
  attachmentIds?: readonly string[];
  sttProvider?: string | null;
  hitlDecision?: unknown;
  directive?: unknown;
  live?: unknown;
  composition?: unknown;
}

/**
 * Whether a send is plain typed text, the only thing that can wait its turn.
 *
 * @param extras - What the send carries beyond its text.
 * @returns True when nothing but the words would leave.
 */
export function isQueueable(extras: SendExtras): boolean {
  return (
    !(extras.attachmentIds && extras.attachmentIds.length > 0) &&
    !extras.sttProvider &&
    !extras.hitlDecision &&
    !extras.directive &&
    !extras.live &&
    !extras.composition
  );
}

/** Where the composer sends words. */
export type ComposerRoute = 'send' | 'queue';

/**
 * Where the composer sends words.
 *
 * While LIA works they wait. On a free account they join what already waits
 * (and leave with it), unless a question is pending: words written after the
 * question are its answer, and what waited never is.
 *
 * @param flags - The account and discussion as the page knows them.
 * @returns `queue` to keep the words with the discussion, `send` otherwise.
 */
export function composerRoute(flags: {
  busy: boolean;
  waiting: boolean;
  questionPending: boolean;
  queueable: boolean;
}): ComposerRoute {
  if (!flags.queueable) return 'send';
  if (flags.busy) return 'queue';
  if (flags.questionPending) return 'send';
  return flags.waiting ? 'queue' : 'send';
}

/**
 * The i18n key of the sentence saying where a waiting message stands.
 *
 * @param message - The waiting message.
 * @param questionPending - A question waits for the person's answer in this discussion.
 * @returns A key under `chat.waiting`.
 */
export function waitingLineKey(message: WaitingMessage, questionPending: boolean): string {
  if (message.status === 'departing') return 'chat.waiting.line_departing';
  if (message.status === 'joining') return 'chat.waiting.line_joining';
  if (questionPending) return 'chat.waiting.line_after_question';
  if (message.status === 'held') return 'chat.waiting.line_held';
  if (message.send_requested) return 'chat.waiting.line_send_requested';
  return 'chat.waiting.line_waiting';
}

/**
 * The actions a waiting message offers.
 *
 * Nothing while it is being sent. A note joining the answer can still be
 * changed or withdrawn until LIA reads it, and nothing else. Never « Send now »
 * or « Add to the answer » while a question waits for its answer; « Send now »
 * once only; « Add to the answer » only while that answer takes notes.
 *
 * @param message - The waiting message.
 * @param questionPending - A question waits for the person's answer in this discussion.
 * @returns Which of edit, withdraw, send now and join are offered.
 */
export function waitingActions(
  message: WaitingMessage,
  questionPending: boolean
): { edit: boolean; withdraw: boolean; sendNow: boolean; join: boolean } {
  const open = message.status !== 'departing';
  const pending = message.status === 'waiting' || message.status === 'held';
  const free = pending && !questionPending;
  return {
    edit: open,
    withdraw: open,
    sendNow: free && !message.send_requested,
    join: free && message.can_join,
  };
}

/**
 * The run a streamed chunk belongs to (every chunk carries its invocation).
 *
 * @param metadata - The chunk's metadata.
 * @returns Its stream id, or null.
 */
export function streamIdOf(metadata: unknown): string | null {
  if (typeof metadata !== 'object' || metadata === null || !('stream_id' in metadata)) return null;
  const value = metadata.stream_id;
  return typeof value === 'string' && value !== '' ? value : null;
}
