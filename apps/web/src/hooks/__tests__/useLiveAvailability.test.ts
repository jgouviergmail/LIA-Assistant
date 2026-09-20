/**
 * useLiveAvailability — the header's « is there one, and on which provider? »:
 * available only under the instance flag AND with at least one ACTIVE live
 * connector (a connector in error is a key to fix, not a live mode), the
 * provider being the one the sessions open on; the read is not even made
 * when the flag is off.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { bumpRevision, useRevisionStore } from '@/stores/revisionStore';

const h = vi.hoisted(() => ({
  liveEnabled: true,
  connectors: undefined as unknown,
  reads: [] as boolean[],
  deps: [] as unknown[][],
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: { features: { live_enabled: h.liveEnabled } } }),
}));
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (_url: string, options: { enabled: boolean; deps?: unknown[] }) => {
    h.reads.push(options.enabled);
    h.deps.push(options.deps ?? []);
    return { data: options.enabled ? h.connectors : undefined, loading: false, error: null };
  },
}));

import { useLiveAvailability } from '../useLiveAvailability';

describe('useLiveAvailability', () => {
  beforeEach(() => {
    h.liveEnabled = true;
    h.connectors = undefined;
    h.reads = [];
    h.deps = [];
    useRevisionStore.setState({ revisions: { live_connectors: 0 } });
  });

  it('is false and reads nothing when the instance flag is off', () => {
    h.liveEnabled = false;
    const { result } = renderHook(() => useLiveAvailability());
    expect(result.current).toEqual({ available: false, provider: null, directTools: false });
    expect(h.reads).toEqual([false]);
  });

  it('is unavailable with no connector or only a broken one, and names the chosen provider once one is active', () => {
    h.connectors = { connectors: [], active_provider: null };
    expect(renderHook(() => useLiveAvailability()).result.current).toEqual({
      available: false,
      provider: null,
      directTools: false,
    });
    h.connectors = {
      connectors: [{ provider: 'gemini', status: 'error', capabilities: { direct_tools: true } }],
      active_provider: 'gemini',
    };
    // A broken connector names no provider either: the entry would open nothing.
    expect(renderHook(() => useLiveAvailability()).result.current).toEqual({
      available: false,
      provider: null,
      directTools: false,
    });
    h.connectors = {
      connectors: [
        { provider: 'gemini', status: 'error', capabilities: { direct_tools: true } },
        { provider: 'openai', status: 'active', capabilities: { direct_tools: false } },
      ],
      active_provider: 'openai',
    };
    expect(renderHook(() => useLiveAvailability()).result.current).toEqual({
      available: true,
      provider: 'openai',
      directTools: false,
    });
  });

  it("offers the direct session on the CHOSEN connector's capability, never on another one", () => {
    // ADR-300 wave 4: a capability of the model the sessions open on — a
    // second active connector whose model could hold one changes nothing.
    h.connectors = {
      connectors: [
        { provider: 'gemini', status: 'active', capabilities: { direct_tools: true } },
        { provider: 'openai', status: 'active', capabilities: { direct_tools: false } },
      ],
      active_provider: 'gemini',
    };
    expect(renderHook(() => useLiveAvailability()).result.current).toEqual({
      available: true,
      provider: 'gemini',
      directTools: true,
    });
    h.connectors = { ...(h.connectors as object), active_provider: 'openai' };
    expect(renderHook(() => useLiveAvailability()).result.current.directTools).toBe(false);
  });

  it('re-reads the connectors when the Live settings declare them changed (owner request 2026-09-19)', () => {
    // The header lives in the dashboard layout and never remounts on the way
    // back from the settings: the revision the writers bump is the query's
    // dependency, so a provider or model change reaches the voice menu.
    h.connectors = {
      connectors: [{ provider: 'gemini', status: 'active', capabilities: { direct_tools: true } }],
      active_provider: 'gemini',
    };
    const { result } = renderHook(() => useLiveAvailability());
    expect(result.current.provider).toBe('gemini');
    expect(h.deps.at(-1)).toEqual([0]);
    h.connectors = {
      connectors: [
        { provider: 'gemini', status: 'active', capabilities: { direct_tools: true } },
        { provider: 'elevenlabs', status: 'active', capabilities: { direct_tools: false } },
      ],
      active_provider: 'elevenlabs',
    };
    act(() => bumpRevision('live_connectors'));
    expect(h.deps.at(-1)).toEqual([1]);
    expect(result.current).toEqual({ available: true, provider: 'elevenlabs', directTools: false });
  });
});
