import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useHomeLocationSettings, type HomeLocation } from '../useHomeLocationSettings';

const { get, put, remove, useAuth, success, error } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  remove: vi.fn(),
  useAuth: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, put, delete: remove } };
});
vi.mock('sonner', () => ({ toast: { success, error } }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const first: HomeLocation = { address: 'First private home', lat: 1, lon: 2 };
const second: HomeLocation = { address: 'Second private home', lat: 3, lon: 4 };

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValueOnce(first).mockResolvedValue(second);
});

describe('saved home location account lifetime', () => {
  it('keeps the new account address input when the previous save completes', async () => {
    let finish: ((value: HomeLocation) => void) | undefined;
    put.mockImplementationOnce(
      () =>
        new Promise<HomeLocation>(resolve => {
          finish = resolve;
        })
    );
    const { result, rerender } = renderHook(() => useHomeLocationSettings('fr'));
    await waitFor(() => expect(result.current.homeLocation).toEqual(first));
    act(() => {
      result.current.setHomeAddressInput('New first home');
    });
    const oldSave = result.current.handleSaveHomeLocation;
    let saving: Promise<void> | undefined;
    act(() => {
      saving = oldSave();
    });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(result.current.homeLocation).toEqual(second));
    act(() => {
      result.current.setHomeAddressInput('Unsent second home');
    });
    await act(async () => {
      finish?.(first);
      await saving;
    });
    expect(result.current.homeAddressInput).toBe('Unsent second home');
    expect(result.current.homeLocation).toEqual(second);
    expect(success).not.toHaveBeenCalled();
    await act(async () => {
      await oldSave();
    });
    expect(put).toHaveBeenCalledTimes(1);
  });

  it('does not revive a previous input after returning to the same account', async () => {
    const { result, rerender } = renderHook(() => useHomeLocationSettings('fr'));
    await waitFor(() => expect(result.current.homeLocation).toEqual(first));
    act(() => {
      result.current.setHomeAddressInput('Previous private draft');
    });
    const oldClear = result.current.handleClearHomeLocation;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    await waitFor(() => expect(result.current.homeLocation).toEqual(second));
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    expect(result.current.homeAddressInput).toBe('');
    await act(async () => {
      await oldClear();
    });
    expect(remove).not.toHaveBeenCalled();
  });
});
