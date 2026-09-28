/**
 * Saving a slot whose engine a reader elsewhere shows makes that reader re-read:
 * the radio's settings offer the voices of the engine the `radio_voice` slot names.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useRevisionStore } from '@/stores/revisionStore';
import { useLLMConfig } from '../useLLMConfig';

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

afterEach(() => vi.clearAllMocks());

function serve(): void {
  mockApi.get.mockImplementation(async (endpoint: string) => {
    if (endpoint.startsWith('/admin/llm-config/types')) return { configs: [] };
    if (endpoint.startsWith('/admin/llm-config/providers')) return { providers: [] };
    return { providers: {} };
  });
  mockApi.put.mockResolvedValue({});
  mockApi.post.mockResolvedValue({});
}

function radioVoices(): number {
  return useRevisionStore.getState().revisions.radio_voices;
}

describe('useLLMConfig — the radio voice slot', () => {
  it('makes the radio settings re-read when the radio voice slot is saved or reset', async () => {
    serve();
    const { result } = renderHook(() => useLLMConfig());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = radioVoices();

    await act(async () => {
      await result.current.updateConfig('radio_voice', { provider: 'edge', model: 'edge-tts' });
    });
    expect(radioVoices()).toBe(before + 1);

    await act(async () => {
      await result.current.resetConfig('radio_voice');
    });
    expect(radioVoices()).toBe(before + 2);
  });

  it('leaves the radio settings alone when another slot is saved', async () => {
    serve();
    const { result } = renderHook(() => useLLMConfig());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = radioVoices();

    await act(async () => {
      await result.current.updateConfig('response', { provider: 'openai', model: 'gpt' });
      await result.current.resetConfig('voice_tts');
    });

    expect(radioVoices()).toBe(before);
  });
});
