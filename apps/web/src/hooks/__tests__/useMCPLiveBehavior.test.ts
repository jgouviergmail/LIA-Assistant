/**
 * useMCPLiveBehavior — the synthesis follows the form before saving (spec 2026-10-30 § 4).
 *
 * Untouched, the form shows what the server does now (the stored synthesis). A change
 * is previewed by the API once the person pauses — never per keystroke, never a late
 * answer for an older choice over a newer one — and a preview that fails says so and
 * falls back to what is stored, never to a guess.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook } from '@/__tests__/test-utils';
import { mcpBehaviorFixture, mcpToolBehaviorFixture } from '@/__tests__/fixtures/mcp-behavior';
import type { MCPBehaviorCandidates, MCPBehaviorPreview } from '@/lib/mcp-behavior';

const { useMCPServerBehavior, useMCPBehaviorPreview } = vi.hoisted(() => ({
  useMCPServerBehavior: vi.fn(),
  useMCPBehaviorPreview: vi.fn(),
}));
vi.mock('@/hooks/useMCPServerBehavior', () => ({ useMCPServerBehavior, useMCPBehaviorPreview }));

import { MCP_PREVIEW_DELAY_MS, useMCPLiveBehavior } from '../useMCPLiveBehavior';

const STORED = mcpBehaviorFixture();
const ASKS_ALWAYS = mcpBehaviorFixture({
  confirmation: { always: true, source: 'server' },
  tools: [mcpToolBehaviorFixture({ reason: 'server_always' })],
});
const AS_DECLARED = mcpBehaviorFixture({
  tools: [mcpToolBehaviorFixture({ reason: 'declared_destructive' })],
  notes: ['server_overrides_account'],
});

const previewServer =
  vi.fn<(id: string, c: MCPBehaviorCandidates) => Promise<MCPBehaviorPreview>>();
const refetch = vi.fn();

function answer(behavior = ASKS_ALWAYS): Promise<MCPBehaviorPreview> {
  return Promise.resolve({ behavior, questions_lost: [] });
}

/** A preview whose answer the test releases when it decides. */
function deferred() {
  let release!: (value: MCPBehaviorPreview) => void;
  let fail!: (error: Error) => void;
  const promise = new Promise<MCPBehaviorPreview>((resolve, reject) => {
    release = resolve;
    fail = reject;
  });
  return { promise, release, fail };
}

function setup(serverId: string | null, candidates: MCPBehaviorCandidates) {
  return renderHook(
    ({ id, values }: { id: string | null; values: MCPBehaviorCandidates }) =>
      useMCPLiveBehavior(id, values),
    { initialProps: { id: serverId, values: candidates } }
  );
}

async function pause() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(MCP_PREVIEW_DELAY_MS);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  useMCPServerBehavior.mockReturnValue({ behavior: STORED, loading: false, error: null, refetch });
  useMCPBehaviorPreview.mockReturnValue({ previewServer, previewStrategy: vi.fn() });
  previewServer.mockImplementation(() => answer());
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useMCPLiveBehavior', () => {
  it('untouched, shows the stored synthesis and previews nothing', async () => {
    const { result } = setup('s1', {});
    await pause();

    expect(result.current.behavior).toBe(STORED);
    expect(result.current.updating).toBe(false);
    expect(previewServer).not.toHaveBeenCalled();
  });

  it('previews a change once the person pauses, then shows its synthesis', async () => {
    const { result } = setup('s1', { hitl_required: true });

    expect(previewServer).not.toHaveBeenCalled();
    expect(result.current.updating).toBe(true);
    await pause();

    expect(previewServer).toHaveBeenCalledTimes(1);
    expect(previewServer).toHaveBeenCalledWith('s1', { hitl_required: true });
    expect(result.current.behavior).toBe(ASKS_ALWAYS);
    expect(result.current.updating).toBe(false);
  });

  it('keeps the last synthesis shown while the next one is computed', async () => {
    const { result, rerender } = setup('s1', { hitl_required: true });
    await pause();
    const pending = deferred();
    previewServer.mockImplementation(() => pending.promise);

    rerender({ id: 's1', values: { hitl_required: false } });
    await pause();

    expect(result.current.behavior).toBe(ASKS_ALWAYS);
    expect(result.current.updating).toBe(true);
    await act(async () => pending.release({ behavior: AS_DECLARED, questions_lost: [] }));
    expect(result.current.behavior).toBe(AS_DECLARED);
  });

  it('a choice changed before the pause previews only the last one', async () => {
    const { rerender } = setup('s1', { hitl_required: true });
    rerender({ id: 's1', values: { hitl_required: false } });
    await pause();

    expect(previewServer).toHaveBeenCalledTimes(1);
    expect(previewServer).toHaveBeenCalledWith('s1', { hitl_required: false });
  });

  it('never shows a late answer for an older choice over a newer one', async () => {
    const older = deferred();
    previewServer.mockImplementationOnce(() => older.promise);
    const { result, rerender } = setup('s1', { hitl_required: true });
    await pause();

    rerender({ id: 's1', values: { hitl_required: false } });
    previewServer.mockImplementation(() => answer(AS_DECLARED));
    await pause();
    await act(async () => older.release({ behavior: ASKS_ALWAYS, questions_lost: [] }));

    expect(result.current.behavior).toBe(AS_DECLARED);
  });

  it('back to the stored values, shows the stored synthesis at once', async () => {
    const { result, rerender } = setup('s1', { hitl_required: true });
    await pause();

    rerender({ id: 's1', values: {} });

    expect(result.current.behavior).toBe(STORED);
    expect(result.current.updating).toBe(false);
  });

  it('after a return to the stored values, a new change never shows an older preview', async () => {
    const { result, rerender } = setup('s1', { hitl_required: true });
    await pause();
    rerender({ id: 's1', values: {} });
    previewServer.mockImplementation(() => deferred().promise);

    rerender({ id: 's1', values: { hitl_required: false } });
    await pause();

    expect(result.current.updating).toBe(true);
    expect(result.current.behavior).toBe(STORED);
  });

  it('a preview that fails falls back to the stored synthesis and says so', async () => {
    previewServer.mockImplementation(() => Promise.reject(new Error('boom')));
    const { result } = setup('s1', { hitl_required: true });
    await pause();

    expect(result.current.behavior).toBe(STORED);
    expect(result.current.previewFailed).toBe(true);
    expect(result.current.updating).toBe(false);
  });

  it('a failed first read is no longer reported once a preview shows a synthesis', async () => {
    useMCPServerBehavior.mockReturnValue({
      behavior: undefined,
      loading: false,
      error: new Error('down'),
      refetch,
    });
    const { result } = setup('s1', { hitl_required: true });
    expect(result.current.loadFailed).toBe(true);
    await pause();

    expect(result.current.behavior).toBe(ASKS_ALWAYS);
    expect(result.current.loadFailed).toBe(false);
  });

  it('refresh re-reads the stored synthesis and previews the current change again', async () => {
    const { result } = setup('s1', { hitl_required: true });
    await pause();

    act(() => result.current.refresh());
    await pause();

    expect(refetch).toHaveBeenCalledTimes(1);
    expect(previewServer).toHaveBeenCalledTimes(2);
  });

  it('a server not yet created previews nothing', async () => {
    const { result } = setup(null, { hitl_required: true });
    await pause();

    expect(previewServer).not.toHaveBeenCalled();
    expect(result.current.updating).toBe(false);
  });
});
