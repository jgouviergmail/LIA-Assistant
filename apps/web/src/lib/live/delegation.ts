/**
 * The bridge between the voice's one function and the chat's door (ADR-299,
 * spec A3; wave 2 spec A7).
 *
 * `send_to_lia(request)` arrives as a delegation; the bridge sends the request
 * through the chat exactly as a typed message (the delegated turn draws itself
 * in the thread), waits for the stream to end, and hands the voice a bounded,
 * flattened answer — or LIA's pending question, which IS the result. The
 * rules, each a test:
 *
 *  - the NEWEST request wins: a delegation arriving while one runs STOPS the
 *    running chat turn (the person corrected or added something; the model
 *    wrote the complete new request, or the transcript window carries it),
 *    closes the old call silently towards the voice (`superseded`) and runs
 *    the new one — the person is never made to wait for an answer they no
 *    longer want (measured 2026-09-18: « the weather on Monday … no, Tuesday »
 *    waited for Monday's);
 *  - a server cancellation (the person interrupted the model with a call
 *    pending) stops the chat turn too, and the cancelled call is never answered;
 *  - a bounded wait, after which the turn goes on in the chat and its answer
 *    is handed back LATE (measured 2026-09-18: a text pushed after a tool call
 *    is spoken) — unless the turn was replaced or cancelled meanwhile;
 *  - a failed turn is reported as FAILED (the server-side bridge's own word,
 *    ADR-301), never as an exception at the voice — nor as « still working »
 *    about a turn that will never land in the chat;
 *  - an empty request is answered without a turn.
 */
import { htmlToPlainText } from '@/lib/html-plain-text';

import type { LiveDelegation, LiveDelivery } from './types';

export interface DelegationLines {
  timed_out: string;
  result_cut: string;
  superseded: string;
  empty_request: string;
  /** A turn that failed (ADR-301: the server-side bridge's word); `timed_out` stands in when unpublished. */
  failed?: string;
}

export interface DelegationDeps {
  /** Send through the chat's own door; resolves when the stream ends. */
  send: (request: string, spokenText: string | null) => Promise<void>;
  /** Stop the chat's running turn (the chat's own Stop). */
  stop: () => Promise<void>;
  /**
   * The last assistant answer, the pending question and the register the
   * answer was said in (ADR-253), read AFTER the stream ended.
   */
  readAnswer: () => Promise<ReadAnswer> | ReadAnswer;
  lines: DelegationLines;
  /** The delivery note per register (from `/live/config`); an unknown register hands none. */
  toneLines?: Record<string, string>;
  timeoutMs: number;
  /** The API's published budget for what the voice is handed. */
  resultMaxTokens: number;
  /** How the person wants a delegated answer delivered (their preference). */
  delivery: LiveDelivery;
  /** The answer of a turn that outlived the wait, to be spoken as a late text. */
  late?: (result: string) => void;
  /** The in-flight turn ended (answered, failed, replaced, or timed out and then finished). */
  idle?: () => void;
  /** A call the newest request replaced: closed towards the voice, silently. */
  superseded?: (id: string) => void;
}

export interface ReadAnswer {
  text: string;
  pendingQuestion: string | null;
  register?: string | null;
}

export interface DelegationResult {
  id: string;
  result: string;
  delivery: LiveDelivery;
  /** How LIA said the answer, for the voice to take that manner — null when unknown. */
  note: string | null;
}

/** Characters per token the project's estimator assumes for Latin text. */
const CHARS_PER_TOKEN = 4;

/** How long a replaced turn is given to end after its Stop before the new one starts. */
export const SUPERSEDE_GRACE_MS = 3_000;

const CJK_RE = /[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]/;

/** What one character costs: an ideograph is a token (ADR-274), four Latin characters are one. */
export function charTokenCost(char: string): number {
  return CJK_RE.test(char) ? 1 : 1 / CHARS_PER_TOKEN;
}

/** A rough token count, on `charTokenCost`. */
export function estimateTokens(text: string): number {
  let tokens = 0;
  let latin = 0;
  for (const char of text) {
    if (CJK_RE.test(char)) tokens += 1;
    else latin += 1;
  }
  return tokens + Math.ceil(latin / CHARS_PER_TOKEN);
}

/**
 * Cut `text` under `maxTokens`, at a word boundary when one exists, and state
 * the cut with `cutLine`.
 */
export function boundToTokens(text: string, maxTokens: number, cutLine: string): string {
  if (estimateTokens(text) <= maxTokens) return text;
  let kept = '';
  let tokens = 0;
  for (const char of text) {
    const cost = charTokenCost(char);
    if (tokens + cost > maxTokens) break;
    tokens += cost;
    kept += char;
  }
  const lastSpace = kept.lastIndexOf(' ');
  if (lastSpace > 0 && !CJK_RE.test(kept)) kept = kept.slice(0, lastSpace);
  return `${kept.trimEnd()} ${cutLine}`;
}

/** Markdown, HTML documents and cards → the prose a voice can say. */
export function flattenForVoice(content: string): string {
  return htmlToPlainText(content)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/^#{1,6}\s+(.+)$/gm, '$1.')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_`~]+/g, '')
    .replace(/^\s*[-*+•]\s+(.+)$/gm, '$1.')
    .replace(/^\s*\d+[.)]\s+(.+)$/gm, '$1.')
    .replace(/\.{2,}/g, '.')
    .replace(/\s+/g, ' ')
    .trim();
}

type TurnState = 'done' | 'failed';

interface InFlight {
  id: string;
  turn: Promise<TurnState>;
}

function sleep(ms: number): Promise<'timeout'> {
  return new Promise(resolve => setTimeout(() => resolve('timeout'), ms));
}

export class DelegationBridge {
  private inFlight: InFlight | null = null;
  /** Calls the server cancelled: never answered. */
  private readonly cancelled = new Set<string>();
  /** Calls a newer request replaced: closed silently once their turn ends. */
  private readonly replaced = new Set<string>();

  constructor(private readonly deps: DelegationDeps) {}

  get busy(): boolean {
    return this.inFlight !== null;
  }

  /** The server cancelled these calls (the person interrupted): stop the running turn. */
  cancel(ids: string[]): void {
    for (const id of ids) this.cancelled.add(id);
    if (this.inFlight && ids.includes(this.inFlight.id)) void this.deps.stop();
  }

  /** Resolves to the answer, or null when the call was cancelled or replaced meanwhile. */
  async handle(call: LiveDelegation, spokenText: string | null): Promise<DelegationResult | null> {
    const request = (call.request ?? '').trim();
    if (!request) return this.answer(call, this.deps.lines.empty_request);
    if (this.inFlight) await this.supersede(this.inFlight);
    const turn = this.runTurn(call, request, spokenText);
    this.inFlight = { id: call.id, turn };
    const outcome = await Promise.race([turn, sleep(this.deps.timeoutMs)]);
    if (this.closedSilently(call.id)) return null;
    if (outcome === 'timeout') {
      // The turn goes on in the chat; its answer will be handed back late —
      // unless the call is replaced or cancelled before it ends.
      void turn.then(async state => {
        if (state === 'done' && !this.closedSilently(call.id)) {
          // A late answer is a text turn: it carries no note (the wire has no room for one).
          this.deps.late?.((await this.result()).result);
        }
      });
      return this.answer(call, this.deps.lines.timed_out);
    }
    if (outcome === 'failed') {
      return this.answer(call, this.deps.lines.failed ?? this.deps.lines.timed_out);
    }
    const { result, note } = await this.result();
    return this.answer(call, result, note);
  }

  /** The newest request wins: stop the running turn, close its call silently, wait for it to end. */
  private async supersede(previous: InFlight): Promise<void> {
    this.replaced.add(previous.id);
    await this.deps.stop();
    await Promise.race([previous.turn, sleep(SUPERSEDE_GRACE_MS)]);
    if (this.inFlight?.id === previous.id) this.inFlight = null;
  }

  /**
   * Whether the call must not be answered by its own result: cancelled by the
   * server (silence), or replaced by a newer request (closed as superseded).
   */
  private closedSilently(id: string): boolean {
    if (this.cancelled.delete(id)) {
      this.replaced.delete(id);
      return true;
    }
    if (this.replaced.delete(id)) {
      this.deps.superseded?.(id);
      return true;
    }
    return false;
  }

  private async runTurn(
    call: LiveDelegation,
    request: string,
    spokenText: string | null
  ): Promise<TurnState> {
    try {
      await this.deps.send(request, spokenText);
      return 'done';
    } catch {
      return 'failed';
    } finally {
      if (this.inFlight?.id === call.id) {
        this.inFlight = null;
        this.deps.idle?.();
      }
    }
  }

  /**
   * What the voice is handed once the turn ended: the question, else the
   * bounded answer — with the delivery note of the register it was said in.
   */
  private async result(): Promise<{ result: string; note: string | null }> {
    const { text, pendingQuestion, register } = await this.deps.readAnswer();
    const note = (register && this.deps.toneLines?.[register]) || null;
    if (pendingQuestion) return { result: pendingQuestion, note };
    return {
      result: boundToTokens(
        flattenForVoice(text),
        this.deps.resultMaxTokens,
        this.deps.lines.result_cut
      ),
      note,
    };
  }

  private answer(
    call: LiveDelegation,
    result: string,
    note: string | null = null
  ): DelegationResult {
    return { id: call.id, result, delivery: this.deps.delivery, note };
  }
}
