import { StrictMode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readPublicUiJson } from '@/lib/api-client';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { useAvatarStyleRollout } from '../useAvatarStyleRollout';

vi.mock('@/lib/api-client', () => ({ readPublicUiJson: vi.fn() }));
const read = vi.mocked(readPublicUiJson);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  useEyesWidgetStore.setState({ appliedAvatarStyleRolloutId: null });
  useEyesWidgetStore.getState().reset();
  useEyesWidgetStore.getState().setStyle('cozmo');
  read.mockResolvedValue({ avatarStyleRolloutId: 'production-bip-v3' });
});
afterEach(() => vi.unstubAllGlobals());

describe('authenticated avatar campaign', () => {
  it('applies the campaign after hydration, once, and preserves a later choice across remounts', async () => {
    const first = renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(useEyesWidgetStore.getState().style).toBe('bip'));
    act(() => useEyesWidgetStore.getState().setStyle('billes'));
    first.unmount();
    renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(useEyesWidgetStore.getState().style).toBe('billes');
  });

  it.each([null, {}, { avatarStyleRolloutId: '' }, { avatarStyleRolloutId: 42 }])(
    'leaves the saved choice alone for unavailable/invalid configuration %j',
    async config => {
      read.mockResolvedValue(config);
      renderHook(useAvatarStyleRollout);
      await waitFor(() => expect(read).toHaveBeenCalledOnce());
      expect(useEyesWidgetStore.getState().style).toBe('cozmo');
      expect(useEyesWidgetStore.getState().appliedAvatarStyleRolloutId).toBeNull();
    }
  );

  it('leaves preferences alone when the configuration request fails', async () => {
    read.mockRejectedValue(new Error('unavailable'));
    renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(read).toHaveBeenCalledOnce());
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
  });

  it('does not send StrictMode cancelled probes or requests after an immediate unmount', async () => {
    const abandoned = renderHook(useAvatarStyleRollout);
    abandoned.unmount();
    await act(async () => Promise.resolve());
    expect(read).not.toHaveBeenCalled();
    renderHook(useAvatarStyleRollout, { wrapper: StrictMode });
    await waitFor(() => expect(useEyesWidgetStore.getState().style).toBe('bip'));
    expect(read).toHaveBeenCalledOnce();
  });

  it('aborts the lifecycle and ignores a late response after unmounting', async () => {
    let answer: ((value: unknown) => void) | undefined;
    read.mockImplementation(
      () =>
        new Promise(resolve => {
          answer = resolve;
        })
    );
    const mounted = renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(read).toHaveBeenCalledOnce());
    const signal = read.mock.calls[0][1]?.signal;
    mounted.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => answer?.({ avatarStyleRolloutId: 'production-bip-v3' }));
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
  });

  it('re-reads another tab’s marker and subsequent choice before a delayed response applies', async () => {
    let answer: ((value: unknown) => void) | undefined;
    read.mockImplementation(
      () =>
        new Promise(resolve => {
          answer = resolve;
        })
    );
    renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(read).toHaveBeenCalledOnce());
    localStorage.setItem(
      EYES_WIDGET_PREFS_KEY,
      JSON.stringify({
        state: {
          style: 'billes',
          visible: false,
          size: 'sm',
          appliedAvatarStyleRolloutId: 'production-bip-v3',
        },
        version: 0,
      })
    );
    await act(async () => answer?.({ avatarStyleRolloutId: 'production-bip-v3' }));
    expect(useEyesWidgetStore.getState()).toMatchObject({
      style: 'billes',
      visible: false,
      size: 'sm',
    });
  });

  it('follows another tab’s later choice without writing back or reapplying the campaign', async () => {
    renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(useEyesWidgetStore.getState().style).toBe('bip'));
    const otherTab = JSON.stringify({
      state: {
        style: 'cozmo',
        visible: false,
        size: 'auto',
        appliedAvatarStyleRolloutId: 'production-bip-v3',
      },
      version: 0,
    });
    localStorage.setItem(EYES_WIDGET_PREFS_KEY, otherTab);
    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: EYES_WIDGET_PREFS_KEY,
          storageArea: localStorage,
        })
      )
    );
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toBe(otherTab);
  });

  it('serializes first visits through the browser lock and rechecks the stored marker inside it', async () => {
    const request = vi.fn(
      async (_name: string, options: { signal: AbortSignal }, apply: () => void) => {
        expect(options.signal.aborted).toBe(false);
        // Another tab applied BIP, then the person chose a different character,
        // before this tab acquired the lock.
        localStorage.setItem(
          EYES_WIDGET_PREFS_KEY,
          JSON.stringify({
            state: {
              style: 'billes',
              appliedAvatarStyleRolloutId: 'production-bip-v3',
            },
            version: 0,
          })
        );
        apply();
      }
    );
    vi.stubGlobal('navigator', { locks: { request } });
    renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(request.mock.calls[0][0]).toBe(`${EYES_WIDGET_PREFS_KEY}:avatar-style-rollout`);
    expect(useEyesWidgetStore.getState().style).toBe('billes');
  });

  it('ignores a queued lock callback after the authenticated host unmounts', async () => {
    let apply: (() => void) | undefined;
    const request = vi.fn(
      (_name: string, _options: { signal: AbortSignal }, callback: () => void) => {
        apply = callback;
        return Promise.resolve();
      }
    );
    vi.stubGlobal('navigator', { locks: { request } });
    const mounted = renderHook(useAvatarStyleRollout);
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    mounted.unmount();
    act(() => apply?.());
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
  });
});
