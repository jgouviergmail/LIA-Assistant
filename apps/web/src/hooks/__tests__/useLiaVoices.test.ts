/**
 * useLiaVoices — LIA's voices for one person (ADR-345 amendment 2026-10-14):
 * read once, saved whole, and the answer the server sends is what the page holds.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { LiaVoices } from '@/types/lia-voices';

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
const account = vi.hoisted(() => ({ user: { id: 'voice-owner-a' } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => account }));
vi.mock('@/lib/api-client', () => ({
  default: api,
  ApiError: class ApiError extends Error {},
}));

import { LIA_VOICES_ENDPOINT, useLiaVoices } from '../useLiaVoices';

const VOICE = { voice_id: 'v', label: 'Voice', gender: 'male' as const, language: 'fr' };
const STORED: LiaVoices = {
  available: true,
  engine: 'edge/edge-tts',
  provider: 'edge',
  voices: [VOICE],
  male: null,
  female: null,
  default_male: VOICE,
  default_female: VOICE,
};

describe('useLiaVoices', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    account.user = { id: 'voice-owner-a' };
    api.get.mockResolvedValue(STORED);
  });

  it('reads the voices once', async () => {
    const { result } = renderHook(() => useLiaVoices());
    await waitFor(() => expect(result.current.lia).toEqual(STORED));
    expect(api.get).toHaveBeenCalledWith(LIA_VOICES_ENDPOINT, expect.anything());
  });

  it('saves both genders and adopts what the server answered', async () => {
    api.put.mockResolvedValue({ ...STORED, male: 'v' });
    const { result } = renderHook(() => useLiaVoices());
    await waitFor(() => expect(result.current.lia).toBeDefined());

    await act(() => result.current.save({ male: 'v', female: null }));

    expect(api.put).toHaveBeenCalledWith(LIA_VOICES_ENDPOINT, { male: 'v', female: null });
    expect(result.current.lia?.male).toBe('v');
  });

  it('keeps what it holds when the server refuses', async () => {
    api.put.mockRejectedValue(new Error('refused'));
    const { result } = renderHook(() => useLiaVoices());
    await waitFor(() => expect(result.current.lia).toBeDefined());

    await expect(act(() => result.current.save({ male: 'x', female: null }))).rejects.toThrow(
      'refused'
    );

    expect(result.current.lia?.male).toBeNull();
  });

  it('keeps the latest choice when the first save answers after the second', async () => {
    let answerFirst!: (value: LiaVoices) => void;
    api.put.mockImplementationOnce(
      () =>
        new Promise<LiaVoices>(resolve => {
          answerFirst = resolve;
        })
    );
    api.put.mockResolvedValueOnce({ ...STORED, male: 'm', female: 'f' });
    const { result } = renderHook(() => useLiaVoices());
    await waitFor(() => expect(result.current.lia).toBeDefined());
    let firstSave!: Promise<void>;
    let latestSave!: Promise<void>;
    act(() => {
      firstSave = result.current.save({ male: 'm', female: null });
      latestSave = result.current.save({ male: 'm', female: 'f' });
    });
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    await act(async () => {
      answerFirst({ ...STORED, male: 'm' });
      await Promise.all([firstSave, latestSave]);
    });
    expect(result.current.lia).toMatchObject({ male: 'm', female: 'f' });
    expect(api.put).toHaveBeenLastCalledWith(LIA_VOICES_ENDPOINT, { male: 'm', female: 'f' });
  });

  it('never shows the departing account or starts its queued save on the next account', async () => {
    api.get.mockResolvedValueOnce({ ...STORED, male: 'private-a' });
    api.get.mockResolvedValueOnce({ ...STORED, male: 'current-b' });
    let answerOld!: (value: LiaVoices) => void;
    api.put.mockImplementationOnce(
      () =>
        new Promise<LiaVoices>(resolve => {
          answerOld = resolve;
        })
    );
    api.put.mockResolvedValueOnce({ ...STORED, male: 'queued-a' });
    const { result, rerender } = renderHook(() => useLiaVoices());
    await waitFor(() => expect(result.current.lia?.male).toBe('private-a'));
    let saves!: Promise<PromiseSettledResult<void>[]>;
    act(() => {
      saves = Promise.allSettled([
        result.current.save({ male: 'new-a', female: null }),
        result.current.save({ male: 'queued-a', female: null }),
      ]);
    });
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    account.user = { id: 'voice-owner-b' };
    rerender();
    const visibleAcrossChange = result.current.lia?.male;
    await act(async () => {
      answerOld({ ...STORED, male: 'new-a' });
      await saves;
    });
    expect(['private-a', 'new-a', 'queued-a']).not.toContain(visibleAcrossChange);
    await waitFor(() => expect(result.current.lia?.male).toBe('current-b'));
    expect(api.put).toHaveBeenCalledTimes(1);
  });
});
