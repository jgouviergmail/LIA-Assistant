/**
 * useWorkbenchLights — the lights screen's read and acts (ADR-369, Task 9.2).
 *
 * The bridge is read once; a change is sent, then the bridge is re-read in
 * place (a room or a scene moves many lamps, and the bridge clamps what it
 * takes); a refused change rejects with its refusal and reads nothing — the
 * control that asked shows its previous value again.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { act, renderHook, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import type { WorkbenchLights } from '@/lib/workbench/types';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { useWorkbenchLights } from '../useWorkbenchLights';

const BRIDGE: WorkbenchLights = { rooms: [], lights: [], scenes: [] };

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue(BRIDGE);
  api.post.mockResolvedValue(undefined);
});

async function rendered() {
  const hook = renderHook(() => useWorkbenchLights(true));
  await waitFor(() => expect(hook.result.current.bridge).toEqual(BRIDGE));
  return hook;
}

describe('useWorkbenchLights', () => {
  it('reads the bridge once', async () => {
    await rendered();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get.mock.calls[0]?.[0]).toBe('/workbench/lights');
  });

  it('sends a change, then re-reads the bridge in place', async () => {
    const { result } = await rendered();

    await act(() => result.current.setLight('l1', { on: false }));

    expect(api.post).toHaveBeenCalledWith(
      '/workbench/lights/light',
      { light_id: 'l1', on: false },
      undefined
    );
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    expect(result.current.bridge).toEqual(BRIDGE);
  });

  it('sends a room and a scene to their own routes', async () => {
    const { result } = await rendered();

    await act(() => result.current.setRoom('r1', { brightness: 30 }));
    await act(() => result.current.recallScene('s1'));

    expect(api.post).toHaveBeenCalledWith(
      '/workbench/lights/room',
      { room_id: 'r1', brightness: 30 },
      undefined
    );
    expect(api.post).toHaveBeenCalledWith('/workbench/lights/scene', { scene_id: 's1' }, undefined);
  });

  it('rejects a refused change with its refusal and reads nothing', async () => {
    const { result } = await rendered();
    const refused = new ApiError('refused', 422, {
      detail: { code: 'not_supported_by_provider' },
    });
    api.post.mockRejectedValueOnce(refused);

    await act(async () => {
      await expect(result.current.setLight('l1', { color_hex: '#ff0000' })).rejects.toBe(refused);
    });

    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('reads nothing where the section is not offered', () => {
    renderHook(() => useWorkbenchLights(false));
    expect(api.get).not.toHaveBeenCalled();
  });
});
