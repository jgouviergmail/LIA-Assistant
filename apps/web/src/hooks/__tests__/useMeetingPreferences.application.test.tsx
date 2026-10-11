import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { MeetingPreferences } from '@/types/meetings';

const { get, put, useAuth } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, put }, apiClient: { get, put } };
});
import { useMeetingPreferences } from '../useMeetingPreferences';

const saved: MeetingPreferences = { stt_engine: 'auto', language: 'auto', auto_email: false, keep_audio_hours: 0, default_template_ref: null, keep_audio_hours_max: 24 };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(saved);
});

describe('meeting preferences ownership and native refresh', () => {
  it('rereads only the addressed owner without starting or updating meetings', async () => {
    const { result } = renderHook(() => useMeetingPreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    act(() => publishApplicationResources('two', new Set(['meeting_preferences'])));
    expect(get).toHaveBeenCalledTimes(1);
    get.mockResolvedValueOnce({ ...saved, language: 'fr' });
    act(() => publishApplicationResources('one', new Set(['meeting_preferences'])));
    await waitFor(() => expect(result.current.preferences?.language).toBe('fr'));
    expect(put).not.toHaveBeenCalled();
  });

  it('retains known settings when an addressed reread fails', async () => {
    const { result } = renderHook(() => useMeetingPreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    get.mockRejectedValueOnce(new Error('offline'));
    act(() => publishApplicationResources('one', new Set(['meeting_preferences'])));
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.preferences).toEqual(saved);
  });

  it('refuses an obsolete save callback across A-to-B-to-A before sending a write', async () => {
    const { result, rerender } = renderHook(() => useMeetingPreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    const oldSave = result.current.save;
    useAuth.mockReturnValue({ user: { id: 'two' } }); rerender();
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    useAuth.mockReturnValue({ user: { id: 'one' } }); rerender();
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    await act(async () => expect(await oldSave({ ...saved, language: 'fr' })).toBeNull());
    expect(put).not.toHaveBeenCalled();
  });

  it('hides prior account data and ignores its late save result', async () => {
    let complete: ((value: MeetingPreferences) => void) | undefined;
    put.mockImplementationOnce(() => new Promise<MeetingPreferences>(resolve => { complete = resolve; }));
    const { result, rerender } = renderHook(() => useMeetingPreferences());
    await waitFor(() => expect(result.current.preferences).toEqual(saved));
    let writing: Promise<MeetingPreferences | null> | undefined;
    act(() => { writing = result.current.save({ ...saved, language: 'fr' }); });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    get.mockImplementationOnce(() => new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } }); rerender();
    expect(result.current.preferences).toBeNull();
    await act(async () => { complete?.({ ...saved, language: 'fr' }); expect(await writing).toBeNull(); });
    expect(result.current.preferences).toBeNull();
    expect(result.current.isSaving).toBe(false);
  });
});
