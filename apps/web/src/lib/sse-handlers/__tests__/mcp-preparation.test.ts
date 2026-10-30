/**
 * Personal-server preparation notices (spec 2026-10-21 §5.6, M5).
 *
 * The backend streams `execution_step` chunks with `step_type: "mcp_preparation"`:
 * a generic progress step (drawn by the step accumulator like every other
 * step) and per-server notices — « slow », then its terminal phase — that
 * raise ONE toast per server per run, updated in place, never re-raised once
 * settled (replay, reconnection), grouped past three servers, cleared on an
 * account switch. The name is the person's own words: shown as text, bounded,
 * isolated from the surrounding sentence's direction.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const toastMock = vi.hoisted(() => {
  const fn = vi.fn() as ReturnType<typeof vi.fn> & Record<string, ReturnType<typeof vi.fn>>;
  fn.success = vi.fn();
  fn.warning = vi.fn();
  fn.dismiss = vi.fn();
  return fn;
});
vi.mock('sonner', () => ({ toast: toastMock }));

import { handleDone, handleError, handleExecutionStep } from '@/lib/sse-handlers/handlers';
import {
  MCP_PREPARATION_NAME_MAX_CHARS,
  resetMcpPreparationNotices,
} from '@/lib/sse-handlers/mcp-preparation';
import type { ChatStreamChunk } from '@/types/chat';

import { buildHandlerContext } from './context-fixture';

const FSI = '⁨';
const PDI = '⁩';

function notice(
  key: string,
  server: string,
  phase: string,
  name = `Server ${server}`
): ChatStreamChunk {
  return {
    type: 'execution_step',
    content: '',
    metadata: {
      step_type: 'mcp_preparation',
      i18n_key: key,
      emoji: null,
      server_key: server,
      server_name: name,
      phase,
      elapsed_ms: 10_000,
    },
  };
}

const slow = (server: string, name?: string) =>
  notice('chat.mcp_preparation.slow', server, 'slow', name);
const ready = (server: string) => notice('chat.mcp_preparation.ready', server, 'ready');
const deferred = (server: string) => notice('chat.mcp_preparation.deferred', server, 'deferred');

function run(chunks: ChatStreamChunk[], options: { isReplay?: boolean; run?: string } = {}) {
  const { context } = buildHandlerContext({
    isReplay: options.isReplay ?? false,
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  });
  Object.assign(context, { assistantMessageId: options.run ?? 'run-1' });
  for (const chunk of chunks) handleExecutionStep(chunk, context);
  return context;
}

/** The test `t` echoes its options: the names list a grouped notice was given. */
function groupNames(message: unknown): unknown {
  return JSON.parse(String(message).split('|').slice(1).join('|')).names;
}

/** How the test `t` renders one quoted name. */
const quoted = (name: string) =>
  `chat.mcp_preparation.quoted_name|${JSON.stringify({ name: `${FSI}${name}${PDI}` })}`;

function toastIds(mock: ReturnType<typeof vi.fn>): unknown[] {
  return mock.mock.calls.map(call => (call[1] as { id?: unknown } | undefined)?.id);
}

beforeEach(() => {
  resetMcpPreparationNotices();
  vi.clearAllMocks();
});

describe('preparation notices', () => {
  it('draws the generic step through the progress accumulator, never as a toast', () => {
    const context = run([
      {
        type: 'execution_step',
        content: '',
        metadata: {
          step_type: 'mcp_preparation',
          i18n_key: 'mcp_preparation',
          emoji: '🧩',
          server_key: null,
          server_name: null,
          phase: 'discovering',
          elapsed_ms: 0,
        },
      },
    ]);

    const [line, ...rest] = context.executionStepsRef.current;
    expect(rest).toEqual([]);
    expect(line.startsWith('*🧩 execution.steps.mcp_preparation')).toBe(true);
    expect(toastMock).not.toHaveBeenCalled();
  });

  it('raises one toast per server per run and updates it on its terminal phase', () => {
    const context = run([slow('a'), ready('a')]);

    expect(toastIds(toastMock)).toEqual(['mcp-prep:run-1:a']);
    expect(toastMock.mock.calls[0][1]).toMatchObject({ duration: Infinity });
    expect(toastIds(toastMock.success)).toEqual(['mcp-prep:run-1:a']);
    expect(context.executionStepsRef.current).toEqual([]); // a notice, not a progress step
  });

  it('says a deferred server is left out of this message, as a warning', () => {
    run([slow('a'), deferred('a')]);

    const [message, options] = toastMock.warning.mock.calls[0];
    expect(String(message)).toContain('chat.mcp_preparation.deferred');
    expect(options).toMatchObject({ id: 'mcp-prep:run-1:a' });
  });

  it('ignores a terminal phase for a server that was never slow', () => {
    run([ready('quick')]);

    expect(toastMock).not.toHaveBeenCalled();
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('does not re-raise a settled server notice on replay', () => {
    run([slow('a'), ready('a')]);
    vi.clearAllMocks();

    run([slow('a'), ready('a')], { isReplay: true }); // the reconnection replays the run
    run([slow('a')]); // a late duplicate of the live chunk

    expect(toastMock).not.toHaveBeenCalled();
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('the same server in another run is a new notice', () => {
    run([slow('a'), ready('a')]);
    run([slow('a')], { run: 'run-2' });

    expect(toastIds(toastMock)).toEqual(['mcp-prep:run-1:a', 'mcp-prep:run-2:a']);
  });

  it('groups more than three slow servers', () => {
    run([slow('a'), slow('b'), slow('c'), slow('d')]);

    const groupId = 'mcp-prep:run-1:group';
    expect(toastMock.dismiss.mock.calls.map(call => call[0])).toEqual([
      'mcp-prep:run-1:a',
      'mcp-prep:run-1:b',
      'mcp-prep:run-1:c',
    ]);
    const last = toastMock.mock.calls.at(-1);
    expect(last?.[1]).toMatchObject({ id: groupId });
    expect(String(last?.[0])).toContain('chat.mcp_preparation.slow_group');
    expect(String(last?.[0])).toContain('"count":4');
    // It names them: three in the language's own quotes, then how many others.
    expect(groupNames(last?.[0])).toEqual([
      quoted('Server a'),
      quoted('Server b'),
      quoted('Server c'),
      'chat.mcp_preparation.others|{"count":1}',
    ]);
  });

  it('a grouped run ends on one notice, naming how many were left out', () => {
    run([
      slow('a'),
      slow('b'),
      slow('c'),
      slow('d'),
      ready('a'),
      deferred('b'),
      deferred('c'),
      ready('d'),
    ]);

    const [message, options] = toastMock.warning.mock.calls.at(-1) ?? [];
    expect(options).toMatchObject({ id: 'mcp-prep:run-1:group' });
    expect(String(message)).toContain('chat.mcp_preparation.deferred_group');
    expect(String(message)).toContain('"count":2');
    // Which ones were left out — the person asked to know (owner, 2026-10-29).
    expect(groupNames(message)).toEqual([quoted('Server b'), quoted('Server c')]);
  });

  it('renders a hostile, long or RTL name as text, bounded and isolated', () => {
    const hostile = '<img src=x onerror=alert(1)>';
    const long = 'n'.repeat(MCP_PREPARATION_NAME_MAX_CHARS + 40);
    const rtl = 'خادم الملاحظات';
    run([slow('h', hostile), slow('l', long), slow('r', rtl)]);

    const names = toastMock.mock.calls.map(
      call => JSON.parse(String(call[0]).split('|')[1]).name as string
    );
    expect(names[0]).toBe(`${FSI}${hostile}${PDI}`); // a string: React renders it as text
    expect(names[1]).toBe(`${FSI}${'n'.repeat(MCP_PREPARATION_NAME_MAX_CHARS)}…${PDI}`);
    expect(names[2]).toBe(`${FSI}${rtl}${PDI}`);
  });

  it('clears on account switch', () => {
    run([slow('a')]);
    resetMcpPreparationNotices();

    expect(toastMock.dismiss).toHaveBeenCalledWith('mcp-prep:run-1:a');
    vi.clearAllMocks();
    run([ready('a')]); // the previous account's slow server is forgotten
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('consumes a malformed notice without drawing anything', () => {
    const context = run([
      {
        type: 'execution_step',
        content: '',
        metadata: { step_type: 'mcp_preparation', i18n_key: 'chat.mcp_preparation.slow' },
      },
    ]);

    expect(toastMock).not.toHaveBeenCalled();
    expect(context.executionStepsRef.current).toEqual([]);
  });

  it('a replayed terminal phase closes the remembered notice and raises none', () => {
    run([slow('a'), ready('a')], { isReplay: true });

    expect(toastMock).not.toHaveBeenCalled();
    expect(toastMock.success).not.toHaveBeenCalled();
    expect(toastMock.dismiss).toHaveBeenCalledWith('mcp-prep:run-1:a');
  });

  it('a group whose servers all became ready closes, saying nothing was left out', () => {
    run([slow('a'), slow('b'), slow('c'), slow('d'), ready('a'), ready('b'), ready('c')]);
    vi.clearAllMocks();
    run([ready('d')]);

    expect(toastMock.warning).not.toHaveBeenCalled();
    expect(toastMock.dismiss).toHaveBeenCalledWith('mcp-prep:run-1:group');
  });

  it('closes a grouped run on account switch', () => {
    run([slow('a'), slow('b'), slow('c'), slow('d')]);
    resetMcpPreparationNotices();

    expect(toastMock.dismiss).toHaveBeenCalledWith('mcp-prep:run-1:group');
  });

  it.each([
    ['done', handleDone],
    ['error', handleError],
  ] as const)('a run that ends on %s closes the notices it still shows', (type, end) => {
    const context = run([slow('a'), slow('b'), ready('b')]);
    vi.clearAllMocks();

    end({ type, content: '', metadata: {} }, context);

    expect(toastMock.dismiss).toHaveBeenCalledWith('mcp-prep:run-1:a');
    // A settled notice keeps its own short life.
    expect(toastMock.dismiss).not.toHaveBeenCalledWith('mcp-prep:run-1:b');
    vi.clearAllMocks();
    run([ready('a')]); // the ended run is forgotten
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it('a grouped run that ends closes its group notice', () => {
    const context = run([slow('a'), slow('b'), slow('c'), slow('d')]);
    vi.clearAllMocks();

    handleDone({ type: 'done', content: '', metadata: {} }, context);

    expect(toastMock.dismiss).toHaveBeenCalledWith('mcp-prep:run-1:group');
  });

  it.each([
    { server_key: 7, server_name: 'Seven' },
    { server_key: '', server_name: 'Empty' },
    { server_key: 'x', server_name: 42 },
    { i18n_key: 'chat.mcp_preparation.unknown', server_key: 'x', server_name: 'X' },
    { i18n_key: 3, server_key: 'x', server_name: 'X' },
  ])('consumes a notice with an unreadable server ($server_key) without drawing', fields => {
    run([
      {
        type: 'execution_step',
        content: '',
        metadata: {
          step_type: 'mcp_preparation',
          i18n_key: 'chat.mcp_preparation.slow',
          ...fields,
        },
      },
    ]);

    expect(toastMock).not.toHaveBeenCalled();
  });
});
