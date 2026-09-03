/**
 * Template and preferences hooks: load once, save returns the server's row,
 * a failed save keeps the previous value and exposes the error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import type { MeetingPreferences, MeetingTemplate } from '@/types/meetings';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));
vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: api };
});
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { useMeetingPreferences } from '../useMeetingPreferences';
import { useMeetingTemplate } from '../useMeetingTemplate';

const template: MeetingTemplate = {
  id: null,
  name: 'Default',
  is_builtin_default: true,
  sections: [{ key: 'summary', label: 'Summary', instruction: 'i', kind: 'paragraph' }],
};
const preferences: MeetingPreferences = {
  stt_engine: 'auto',
  language: 'auto',
  auto_email: false,
  keep_audio_hours: 0,
  keep_audio_hours_max: 168,
};

beforeEach(() => {
  Object.values(api).forEach(fn => fn.mockReset());
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useMeetingTemplate', () => {
  it('loads, saves and resets through the API', async () => {
    api.get.mockResolvedValueOnce(template);
    const saved = { ...template, id: 't1', name: 'Mine', is_builtin_default: false };
    api.put.mockResolvedValueOnce(saved);
    api.delete.mockResolvedValueOnce(template);
    const { result } = renderHook(() => useMeetingTemplate());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.template).toEqual(template);

    await act(async () => {
      await result.current.save({ name: 'Mine', sections: template.sections });
    });
    expect(api.put).toHaveBeenCalledWith('/meetings/template', {
      name: 'Mine',
      sections: template.sections,
    });
    expect(result.current.template?.name).toBe('Mine');

    await act(async () => {
      await result.current.reset();
    });
    expect(api.delete).toHaveBeenCalledWith('/meetings/template');
    expect(result.current.template?.is_builtin_default).toBe(true);
  });

  it('a failed save keeps the current template and exposes the error', async () => {
    api.get.mockResolvedValueOnce(template);
    api.put.mockRejectedValueOnce(new Error('422'));
    const { result } = renderHook(() => useMeetingTemplate());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let outcome: MeetingTemplate | null = template;
    await act(async () => {
      outcome = await result.current.save({ name: 'x', sections: template.sections });
    });
    expect(outcome).toBeNull();
    expect(result.current.template).toEqual(template);
    expect(result.current.error?.message).toBe('422');
  });
});

describe('useMeetingPreferences', () => {
  it('loads and saves the preferences', async () => {
    api.get.mockResolvedValueOnce(preferences);
    api.put.mockResolvedValueOnce({ ...preferences, auto_email: true });
    const { result } = renderHook(() => useMeetingPreferences());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.save({
        stt_engine: 'auto',
        language: 'auto',
        auto_email: true,
        keep_audio_hours: 0,
      });
    });
    expect(api.put).toHaveBeenCalledWith('/meetings/preferences', {
      stt_engine: 'auto',
      language: 'auto',
      auto_email: true,
      keep_audio_hours: 0,
    });
    expect(result.current.preferences?.auto_email).toBe(true);
  });

  it('does not fetch when disabled', async () => {
    const { result } = renderHook(() => useMeetingPreferences(false));
    expect(result.current.isLoading).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
  });
});
