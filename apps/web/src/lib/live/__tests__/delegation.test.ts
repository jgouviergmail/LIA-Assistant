/**
 * DelegationBridge — the voice's one function becomes a chat turn (spec A3).
 *
 *  - the request goes through `send` with the spoken text; the result is the
 *    flattened answer, bounded to the token budget, the cut stated;
 *  - the newest request wins: a second call while one runs stops the first
 *    turn, closes its call silently and runs the second;
 *  - a server cancellation of the running call stops the turn, no answer;
 *  - after `timeoutMs` the voice hears `timed_out`, the turn keeps running, and
 *    its late answer is handed back through `late` (measured 2026-09-18: a text
 *    pushed after a tool call is spoken);
 *  - a pending HITL question IS the result;
 *  - a cancelled id is never answered (the turn is never killed here);
 *  - an empty request is answered without a turn.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  DelegationBridge,
  boundToTokens,
  flattenForVoice,
  type DelegationDeps,
} from '../delegation';

const LINES = {
  timed_out: 'TIMED',
  result_cut: '(CUT)',
  superseded: 'SUP',
  empty_request: 'EMPTY',
};

interface Harness {
  deps: DelegationDeps;
  send: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  late: ReturnType<typeof vi.fn>;
  idle: ReturnType<typeof vi.fn>;
  superseded: ReturnType<typeof vi.fn>;
  /** Resolve the pending sends, oldest first. */
  finish: () => void;
}

function harness(overrides: Partial<DelegationDeps> = {}): Harness {
  const resolvers: Array<() => void> = [];
  const send = vi.fn(
    () =>
      new Promise<void>(resolve => {
        resolvers.push(resolve);
      })
  );
  // The chat's Stop ends the running turn: the oldest pending send resolves.
  const stop = vi.fn(async () => {
    resolvers.shift()?.();
  });
  const late = vi.fn();
  const idle = vi.fn();
  const superseded = vi.fn();
  const deps: DelegationDeps = {
    send,
    stop,
    readAnswer: () => ({ text: '**Two** meetings tomorrow.', pendingQuestion: null }),
    lines: LINES,
    timeoutMs: 1_000,
    resultMaxTokens: 100,
    delivery: 'now',
    late,
    idle,
    superseded,
    ...overrides,
  };
  return { deps, send, stop, late, idle, superseded, finish: () => resolvers.shift()?.() };
}

const call = (id = 'c1') => ({ id, request: 'agenda?' });

describe('DelegationBridge', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends the request with the spoken words and returns the flattened answer', async () => {
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const pending = bridge.handle(call(), 'agenda ?');
    expect(h.send).toHaveBeenCalledWith('agenda?', 'agenda ?');
    expect(bridge.busy).toBe(true);
    h.finish();
    const result = await pending;
    expect(result).toEqual({
      id: 'c1',
      result: 'Two meetings tomorrow.',
      delivery: 'now',
      note: null,
    });
    expect(bridge.busy).toBe(false);
    expect(h.late).not.toHaveBeenCalled();
    expect(h.idle).toHaveBeenCalledTimes(1);
  });

  it('the newest request wins: the first turn is stopped, its call closed silently', async () => {
    // « the weather on Monday » … « no, Tuesday »: nobody waits for Monday's.
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const first = bridge.handle(call('c1'), 'monday');
    const second = bridge.handle({ id: 'c2', request: 'weather tuesday' }, 'no, tuesday');
    await vi.waitFor(() => expect(h.stop).toHaveBeenCalledTimes(1));
    expect(await first).toBeNull();
    expect(h.superseded).toHaveBeenCalledWith('c1');
    await vi.waitFor(() => expect(h.send).toHaveBeenCalledTimes(2));
    expect(h.send).toHaveBeenLastCalledWith('weather tuesday', 'no, tuesday');
    h.finish();
    expect((await second)?.result).toBe('Two meetings tomorrow.');
    expect(bridge.busy).toBe(false);
    expect(h.late).not.toHaveBeenCalled();
  });

  it('a replaced turn that had timed out is never spoken late', async () => {
    vi.useFakeTimers();
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const first = bridge.handle(call('c1'), null);
    await vi.advanceTimersByTimeAsync(1_001);
    expect((await first)?.result).toBe('TIMED');
    const second = bridge.handle(call('c2'), null);
    await vi.advanceTimersByTimeAsync(0);
    expect(h.stop).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(10);
    h.finish();
    expect((await second)?.result).toBe('Two meetings tomorrow.');
    await vi.advanceTimersByTimeAsync(10);
    expect(h.late).not.toHaveBeenCalled();
    expect(h.superseded).toHaveBeenCalledWith('c1');
  });

  it('answers an empty request without opening a turn', async () => {
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const result = await bridge.handle({ ...call(), request: '   ' }, null);
    expect(result?.result).toBe('EMPTY');
    expect(h.send).not.toHaveBeenCalled();
  });

  it('times out into timed_out, the turn goes on, and its answer arrives late', async () => {
    vi.useFakeTimers();
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const pending = bridge.handle(call(), null);
    await vi.advanceTimersByTimeAsync(1_001);
    const result = await pending;
    expect(result?.result).toBe('TIMED');
    expect(bridge.busy).toBe(true);
    h.finish();
    await vi.advanceTimersByTimeAsync(0);
    expect(bridge.busy).toBe(false);
    expect(h.idle).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(0);
    expect(h.late).toHaveBeenCalledWith('Two meetings tomorrow.');
  });

  it('hands the delivery note of the register the answer wore, none for an unknown one', async () => {
    // ADR-253 in the voice: the bridge maps the register to the note the API
    // published; a register without a note (or no register) hands none.
    const notes = { warm: 'LIA said this warmly.' };
    const worn = harness({
      toneLines: notes,
      readAnswer: () => ({ text: 'Done.', pendingQuestion: null, register: 'warm' }),
    });
    const pending = new DelegationBridge(worn.deps).handle(call(), null);
    worn.finish();
    expect((await pending)?.note).toBe('LIA said this warmly.');
    const unknown = harness({
      toneLines: notes,
      readAnswer: () => ({ text: 'Done.', pendingQuestion: null, register: 'made-up' }),
    });
    const other = new DelegationBridge(unknown.deps).handle(call(), null);
    unknown.finish();
    expect((await other)?.note).toBeNull();
    // A question from LIA carries its register's note as well.
    const asked = harness({
      toneLines: notes,
      readAnswer: () => ({ text: '', pendingQuestion: 'Send it?', register: 'warm' }),
    });
    const question = new DelegationBridge(asked.deps).handle(call(), null);
    asked.finish();
    expect(await question).toMatchObject({ result: 'Send it?', note: 'LIA said this warmly.' });
  });

  it('a pending question is the result, whole', async () => {
    const h = harness({
      readAnswer: () => ({ text: 'ignored', pendingQuestion: 'Send it to Alex?' }),
    });
    const bridge = new DelegationBridge(h.deps);
    const pending = bridge.handle(call(), null);
    h.finish();
    expect((await pending)?.result).toBe('Send it to Alex?');
  });

  it('bounds the result to the token budget and states the cut', async () => {
    const h = harness({
      readAnswer: () => ({ text: 'word '.repeat(100), pendingQuestion: null }),
      resultMaxTokens: 5,
    });
    const bridge = new DelegationBridge(h.deps);
    const pending = bridge.handle(call(), null);
    h.finish();
    const result = (await pending)?.result ?? '';
    expect(result.endsWith(' (CUT)')).toBe(true);
    expect(result.length).toBeLessThan(40);
  });

  it('a server cancellation stops the running turn and the call is never answered', async () => {
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const pending = bridge.handle(call('c1'), null);
    bridge.cancel(['c1']);
    expect(h.stop).toHaveBeenCalledTimes(1);
    expect(await pending).toBeNull();
    expect(bridge.busy).toBe(false);
    expect(h.late).not.toHaveBeenCalled();
    expect(h.superseded).not.toHaveBeenCalled();
  });

  it('a cancellation of another id stops nothing', async () => {
    const h = harness();
    const bridge = new DelegationBridge(h.deps);
    const pending = bridge.handle(call('c1'), null);
    bridge.cancel(['other']);
    expect(h.stop).not.toHaveBeenCalled();
    h.finish();
    expect((await pending)?.result).toBe('Two meetings tomorrow.');
  });

  it('answers a failed turn with the failed line rather than throwing at the voice', async () => {
    // The server-side bridge names a failure `failed` (ADR-301); the browser
    // says the same thing — never « LIA is still working » about a turn that
    // will never land in the chat.
    const send = vi.fn(async () => Promise.reject(new Error('network')));
    const h = harness({ send, lines: { ...LINES, failed: 'FAILED' } });
    const bridge = new DelegationBridge(h.deps);
    const result = await bridge.handle(call(), null);
    expect(result?.result).toBe('FAILED');
    expect(bridge.busy).toBe(false);
  });

  it('falls back to timed_out for a failed turn when the API published no failed line', async () => {
    const send = vi.fn(async () => Promise.reject(new Error('network')));
    const h = harness({ send });
    const bridge = new DelegationBridge(h.deps);
    const result = await bridge.handle(call(), null);
    expect(result?.result).toBe('TIMED');
  });
});

describe('flattenForVoice', () => {
  it('reduces markdown and cards to prose', () => {
    expect(
      flattenForVoice(
        '# Title\n\n- **one**\n- [two](http://x)\n\n<div class="lia-card"><p>inside</p></div>'
      )
    ).toBe('Title. one. two. inside');
  });

  it('keeps plain prose untouched and drops code fences', () => {
    expect(flattenForVoice('Hello there.')).toBe('Hello there.');
    expect(flattenForVoice('Run this:\n\n```sh\nls -la\n```\n\nthen stop.')).toBe(
      'Run this: then stop.'
    );
  });
});

describe('boundToTokens', () => {
  it('keeps a short text whole and cuts a long one at a word', () => {
    expect(boundToTokens('short text', 10, '(CUT)')).toBe('short text');
    const cut = boundToTokens('alpha beta gamma delta epsilon zeta', 3, '(CUT)');
    expect(cut).toBe('alpha beta (CUT)');
  });

  it('counts an ideograph as one token', () => {
    const cjk = '今天有两个会议，一个在九点，一个在十四点。';
    expect(boundToTokens(cjk, 100, '(CUT)')).toBe(cjk);
    expect(boundToTokens(cjk, 4, '(CUT)')).toBe('今天有两 (CUT)');
  });
});
