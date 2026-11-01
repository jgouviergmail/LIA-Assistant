/**
 * useMCPServerBehavior / useMCPBehaviorPreview — the synthesis of what a server will
 * do, and the previews the page reads before a change (spec 2026-10-30 D5, § 6).
 *
 * The page never computes a confirmation: it reads the API. These tests pin the
 * endpoints, that a server's synthesis is read only while a server is shown, and that
 * an explicit « back to the default » (null) travels as null, never dropped.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';
import { mutateSpy, mutationResult, queryResult } from '@/__tests__/api-mocks';

const { useApplicationAccountQuery } = vi.hoisted(() => ({ useApplicationAccountQuery: vi.fn() }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({ useApplicationAccountQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import {
  useMCPBehaviorPreview,
  useMCPServerBehavior,
  useMCPToolChoice,
} from '../useMCPServerBehavior';

const serverPreview = mutateSpy();
const strategyPreview = mutateSpy();
const toolChoice = mutateSpy();

beforeEach(() => {
  vi.clearAllMocks();
  let cursor = 0;
  const order = [serverPreview, strategyPreview];
  useApiMutation.mockImplementation(({ method }: { method: string }) =>
    mutationResult({ mutate: method === 'PUT' ? toolChoice : order[cursor++ % 2] })
  );
  useApplicationAccountQuery.mockReturnValue({
    ...queryResult({ data: undefined }),
    ownerId: 'owner',
    isCurrent: () => true,
  });
});

describe('useMCPServerBehavior', () => {
  it('reads the shown server synthesis', () => {
    renderHook(() => useMCPServerBehavior('s1'));

    expect(useApplicationAccountQuery).toHaveBeenCalledWith(
      '/mcp/servers/s1/behavior',
      'MCPServerBehavior',
      true
    );
  });

  it('reads nothing while no server is shown', () => {
    renderHook(() => useMCPServerBehavior(null));

    const [, , enabled] = useApplicationAccountQuery.mock.calls[0];
    expect(enabled).toBe(false);
  });
});

describe('useMCPBehaviorPreview', () => {
  it('previews a server under the form candidate values', async () => {
    const { result } = renderHook(() => useMCPBehaviorPreview());

    await act(async () => {
      await result.current.previewServer('s1', { hitl_required: null });
    });

    expect(serverPreview).toHaveBeenCalledWith('/mcp/servers/s1/behavior/preview', {
      hitl_required: null,
    });
  });

  it('keeps both previews stable across renders — an effect may depend on them', () => {
    // The live synthesis re-runs its preview when `previewServer` changes: a new
    // function each render would preview in a loop.
    const { result, rerender } = renderHook(() => useMCPBehaviorPreview());
    const first = result.current;

    rerender();

    expect(result.current.previewServer).toBe(first.previewServer);
    expect(result.current.previewStrategy).toBe(first.previewStrategy);
  });

  it('previews a strategy, an explicit default included', async () => {
    const { result } = renderHook(() => useMCPBehaviorPreview());

    await act(async () => {
      await result.current.previewStrategy(null);
    });

    expect(strategyPreview).toHaveBeenCalledWith('/mcp/servers/strategy/preview', {
      mcp_hitl_required: null,
    });
  });
});

describe('useMCPToolChoice', () => {
  it('writes one tool choice, an explicit default included', async () => {
    const { result } = renderHook(() => useMCPToolChoice());

    await act(async () => {
      await result.current.setToolChoice('s1', 'delete_note', 'never');
      await result.current.setToolChoice('s1', 'read_note', null);
    });

    expect(toolChoice.mock.calls).toEqual([
      ['/mcp/servers/s1/tool-confirmations', { tool_name: 'delete_note', choice: 'never' }],
      ['/mcp/servers/s1/tool-confirmations', { tool_name: 'read_note', choice: null }],
    ]);
  });

  it('is stable across renders', () => {
    const { result, rerender } = renderHook(() => useMCPToolChoice());
    const first = result.current.setToolChoice;

    rerender();

    expect(result.current.setToolChoice).toBe(first);
  });
});
