import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { LiveConnectorResponse } from '@/lib/live/types';

const { get, put, useAuth } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, put } };
});
import { useLiveConnectorSettings } from '../useLiveConnectorSettings';

const connector: LiveConnectorResponse = { provider: 'gemini', connector_type: 'gemini_live', status: 'active',
  settings: { model: 'model', voice: 'Kore', thinking_level: null, idle_timeout_seconds: 60, session_max_minutes: 10, session_budget_eur: null },
  model_settings: {}, active: true, functionally_verified: true,
  capabilities: { async_delegation: true, delivery_scheduling: true, reports_idle: false, cancels_on_interruption: true, configurable_vad: true, resumes: true, thinking: false, direct_tools: false, portal_voice: false, vendor_billed: false },
};
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation(async (path: string) => {
    if (path === '/live/connectors') return { connectors: [connector], active_provider: 'gemini' };
    if (path === '/live/models') return { models: [], default_model: '', unpriced: [] };
    if (path.startsWith('/live/voices')) return { provider: 'gemini', voices: [], provenance: 'published' };
    return {};
  });
});

describe('Live connector settings account and committed change', () => {
  it('refuses a callback from the previous account before provider work', async () => {
    const { result, rerender } = renderHook(() => useLiveConnectorSettings());
    await waitFor(() => expect(result.current.connectors?.connectors).toEqual([connector]));
    const obsolete = result.current.save;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await act(async () => { expect(await obsolete('gemini', connector.settings)).toBe(false); });
    expect(put).not.toHaveBeenCalled();
  });

  it('rereads owned connector settings after native confirmation', async () => {
    const { result } = renderHook(() => useLiveConnectorSettings());
    await waitFor(() => expect(result.current.connectors?.connectors).toEqual([connector]));
    get.mockImplementation(async (path: string) => path === '/live/connectors'
      ? { connectors: [{ ...connector, settings: { ...connector.settings, voice: 'Puck' } }], active_provider: 'gemini' }
      : {});
    act(() => publishApplicationResources('one', new Set(['live_connectors'])));
    await waitFor(() => expect(result.current.connectors?.connectors[0].settings.voice).toBe('Puck'));
  });

  it('serializes saves so the last provider choice cannot be overwritten by an older response', async () => {
    let firstDone: ((value: LiveConnectorResponse) => void) | undefined;
    put.mockImplementationOnce(() => new Promise<LiveConnectorResponse>(done => { firstDone = done; }))
      .mockImplementationOnce(async () => ({ ...connector, settings: { ...connector.settings, voice: 'Puck' } }));
    const { result } = renderHook(() => useLiveConnectorSettings());
    await waitFor(() => expect(result.current.connectors?.connectors).toEqual([connector]));
    let first: Promise<boolean> | undefined;
    let second: Promise<boolean> | undefined;
    act(() => {
      first = result.current.save('gemini', connector.settings);
      second = result.current.save('gemini', { ...connector.settings, voice: 'Puck' });
    });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    await act(async () => { firstDone?.(connector); await first; await second; });
    expect(result.current.connectors?.connectors[0].settings.voice).toBe('Puck');
  });

  it('discards a late write result and its error after changing account', async () => {
    let finish: ((value: LiveConnectorResponse) => void) | undefined;
    put.mockImplementationOnce(() => new Promise<LiveConnectorResponse>(done => { finish = done; }));
    const { result, rerender } = renderHook(() => useLiveConnectorSettings());
    await waitFor(() => expect(result.current.connectors?.connectors).toEqual([connector]));
    let pending: Promise<boolean> | undefined;
    act(() => { pending = result.current.save('gemini', { ...connector.settings, voice: 'Puck' }); });
    await waitFor(() => expect(put).toHaveBeenCalledOnce());
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await act(async () => { finish?.({ ...connector, settings: { ...connector.settings, voice: 'Puck' } }); expect(await pending).toBe(false); });
    await waitFor(() => expect(result.current.connectors?.connectors[0].settings.voice).toBe('Kore'));
    expect(result.current.saveError).toBeNull();
  });

  it('preserves the last saved cards when a native reread fails', async () => {
    const { result } = renderHook(() => useLiveConnectorSettings());
    await waitFor(() => expect(result.current.connectors?.connectors).toEqual([connector]));
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['live_connectors'])));
    await waitFor(() => expect(get.mock.calls.filter(call => call[0] === '/live/connectors')).toHaveLength(2));
    expect(result.current.connectors?.connectors).toEqual([connector]);
  });
});
