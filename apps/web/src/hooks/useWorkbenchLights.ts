'use client';

/**
 * The lights screen's read and acts (ADR-369, Task 9.2).
 *
 * The bridge is read once (rooms, lights, scenes), owner-isolated
 * (`useApplicationAccountQuery`). A change is sent, then the bridge is re-read
 * IN PLACE — a room or a scene moves many lamps, and the bridge clamps what it
 * takes, so the truth is the bridge's. A refused change rejects with its
 * refusal and reads nothing: the control that asked holds its own draft and
 * shows the previous value again when the act fails. A re-read that fails
 * after a change that landed is the listing's own error, never the change's.
 */
import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import type { WorkbenchLights } from '@/lib/workbench/types';

/** What changes on one lamp (`schemas/lights.LightChange`, without its id). */
export interface LightChangeBody {
  on?: boolean;
  brightness?: number;
  color_hex?: string;
  mirek?: number;
}

/** What changes on every light of one room. */
export interface RoomChangeBody {
  on?: boolean;
  brightness?: number;
}

export interface WorkbenchLightsState {
  /** The bridge, once read for the current account. */
  bridge: WorkbenchLights | undefined;
  loading: boolean;
  error: unknown;
  refresh: () => Promise<void>;
  setLight: (lightId: string, change: LightChangeBody) => Promise<void>;
  setRoom: (roomId: string, change: RoomChangeBody) => Promise<void>;
  recallScene: (sceneId: string) => Promise<void>;
}

/**
 * @param enabled - Whether the tool is ready (nothing is read otherwise).
 * @returns The bridge and the screen's acts.
 */
export function useWorkbenchLights(enabled: boolean): WorkbenchLightsState {
  const query = useApplicationAccountQuery<WorkbenchLights>(
    '/workbench/lights',
    'WorkbenchLights',
    enabled
  );
  const { refetch } = query;
  const { mutate: post } = useApiMutation<Record<string, unknown>, void>({
    method: 'POST',
    componentName: 'WorkbenchLights',
  });

  const send = useCallback(
    async (path: string, body: Record<string, unknown>) => {
      await post(path, body);
      // The act landed; a failed re-read is the listing's own error, said there.
      await refetch().catch(() => undefined);
    },
    [post, refetch]
  );

  const setLight = useCallback(
    (lightId: string, change: LightChangeBody) =>
      send('/workbench/lights/light', { light_id: lightId, ...change }),
    [send]
  );
  const setRoom = useCallback(
    (roomId: string, change: RoomChangeBody) =>
      send('/workbench/lights/room', { room_id: roomId, ...change }),
    [send]
  );
  const recallScene = useCallback(
    (sceneId: string) => send('/workbench/lights/scene', { scene_id: sceneId }),
    [send]
  );

  return {
    bridge: query.data,
    loading: query.loading,
    error: query.error,
    refresh: refetch,
    setLight,
    setRoom,
    recallScene,
  };
}
