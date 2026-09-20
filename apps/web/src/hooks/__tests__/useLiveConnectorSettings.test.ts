/**
 * useLiveConnectorSettings — reads nothing but the connectors until one
 * exists; lists the voices of the ACTIVE provider, then of the provider under
 * edit, and never hands over a listing that names another provider (the
 * query hook renders one stale frame on a key change); a save makes the saved
 * connector the one the sessions open on and the others not; a refusal is
 * reported in the server's words.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';
import { useRevisionStore } from '@/stores/revisionStore';

const h = vi.hoisted(() => ({
  table: {} as Record<string, unknown>,
  reads: [] as Array<[string, boolean]>,
  mutate: vi.fn(),
}));

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (url: string, options: { enabled: boolean }) => {
    h.reads.push([url, options.enabled]);
    const [override, setOverride] = useState<unknown>(undefined);
    const served = override ?? h.table[url];
    const setData = (update: unknown) =>
      setOverride((previous: unknown) =>
        typeof update === 'function' ? update(previous ?? h.table[url]) : update
      );
    return {
      data: options.enabled ? served : undefined,
      loading: false,
      error: null,
      refetch: vi.fn(),
      setData,
    };
  },
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: h.mutate, loading: false, error: null, reset: vi.fn() }),
}));

import { useLiveConnectorSettings } from '../useLiveConnectorSettings';

const CAPABILITIES = {
  async_delegation: true,
  delivery_scheduling: true,
  reports_idle: false,
  cancels_on_interruption: true,
  configurable_vad: true,
  resumes: true,
  thinking: false,
};
const GEMINI = {
  provider: 'gemini',
  connector_type: 'gemini_live',
  status: 'active',
  settings: {
    model: 'gemini-x-live',
    voice: 'Kore',
    thinking_level: null,
    session_budget_eur: null,
    idle_timeout_seconds: 60,
    session_max_minutes: 10,
  },
  model_settings: {},
  functionally_verified: true,
  capabilities: CAPABILITIES,
  active: true,
};
const OPENAI = { ...GEMINI, provider: 'openai', connector_type: 'gpt_live', active: false };
const VOICES = (provider: string) => ({
  provider,
  voices: [{ name: 'V', characteristic: '' }],
  provenance: 'published',
  published_at: null,
  source: null,
});

describe('useLiveConnectorSettings', () => {
  beforeEach(() => {
    h.reads = [];
    h.mutate.mockReset();
    useRevisionStore.setState({ revisions: { live_connectors: 0 } });
    h.table = {
      '/live/connectors': { connectors: [GEMINI, OPENAI], active_provider: 'gemini' },
      '/live/models': { models: [], default_model: '', unpriced: [] },
      '/live/config': { session_max_minutes: 10, idle_timeout_seconds: 60 },
      '/live/voices?provider=gemini': VOICES('gemini'),
      '/live/voices?provider=openai': VOICES('gemini'), // a stale answer for the wrong provider
    };
  });

  it('reads only the connectors until the account holds one', () => {
    h.table['/live/connectors'] = { connectors: [], active_provider: null };
    const { result } = renderHook(() => useLiveConnectorSettings(true));
    expect(result.current.connectors).toEqual({ connectors: [], active_provider: null });
    expect(result.current.models).toBeUndefined();
    expect(result.current.config).toBeUndefined();
    expect(h.reads.filter(([url]) => url !== '/live/connectors').every(([, on]) => !on)).toBe(true);
  });

  it('lists the voices of the active provider, then of the one under edit — never a stale listing', () => {
    const { result, rerender } = renderHook(
      ({ edited }: { edited: string | null }) => useLiveConnectorSettings(true, edited),
      { initialProps: { edited: null as string | null } }
    );
    expect(result.current.voices?.provider).toBe('gemini');
    rerender({ edited: 'openai' });
    expect(h.reads.at(-1)?.[0]).toBe('/live/voices?provider=openai');
    // The answer served under that key names gemini: it is withheld, not paired.
    expect(result.current.voices).toBeUndefined();
  });

  it('a save makes the saved connector the active one and the others not', async () => {
    const saved = { ...OPENAI, active: true, settings: { ...OPENAI.settings, voice: 'V' } };
    h.mutate.mockResolvedValueOnce(saved);
    const { result } = renderHook(() => useLiveConnectorSettings(true));
    let ok = false;
    await act(async () => {
      ok = await result.current.save('openai', saved.settings);
    });
    expect(ok).toBe(true);
    expect(h.mutate).toHaveBeenCalledWith('/live/connectors/openai', saved.settings);
    await waitFor(() => expect(result.current.connectors?.active_provider).toBe('openai'));
    expect(result.current.connectors?.connectors.map(c => [c.provider, c.active])).toEqual([
      ['gemini', false],
      ['openai', true],
    ]);
    // The header's menu follows the same resource: a save declares it changed.
    expect(useRevisionStore.getState().revisions.live_connectors).toBe(1);
  });

  it("reports a refusal in the server's words and keeps the choice", async () => {
    h.mutate.mockRejectedValueOnce(
      new ApiError('refused', 422, {
        detail: { code: 'provider_refused', message: 'The provider refused this model: quota' },
      })
    );
    const { result } = renderHook(() => useLiveConnectorSettings(true));
    let ok = true;
    await act(async () => {
      ok = await result.current.save('gemini', GEMINI.settings);
    });
    expect(ok).toBe(false);
    expect(result.current.saveError).toBe('The provider refused this model: quota');
    expect(result.current.connectors?.active_provider).toBe('gemini');
    // Nothing changed server-side: nothing to re-read elsewhere.
    expect(useRevisionStore.getState().revisions.live_connectors).toBe(0);
  });
});
