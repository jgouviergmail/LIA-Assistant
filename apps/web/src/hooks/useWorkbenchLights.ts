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
import type { WorkbenchLights, WorkbenchRoom } from '@/lib/workbench/types';

/** What changes on one lamp (`schemas/lights.LightChange`, without its id). */
export interface LightChangeBody {
  on?: boolean;
  brightness?: number;
  color_hex?: string;
  mirek?: number;
}

/** What changes on every light of one room. */
export interface RoomChangeBody {
  kind?: WorkbenchRoom['kind'];
  on?: boolean;
  brightness?: number;
  color_hex?: string;
  mirek?: number;
}

export interface WorkbenchLightsState {
  /** The bridge, once read for the current account. */
  bridge: WorkbenchLights | undefined;
  loading: boolean;
  error: unknown;
  refresh: () => Promise<void>;
  setLight: (lightId: string, change: LightChangeBody) => Promise<void>;
  setRoom: (roomId: string, change: RoomChangeBody) => Promise<void>;
  /** `play` starts its motion or holds it still; left out, it is shown as it stands. */
  recallScene: (sceneId: string, play?: boolean) => Promise<void>;
  /** @returns How many stayed on. */
  switchAll: (
    on: boolean,
    roomIds: readonly string[],
    lightIds: readonly string[]
  ) => Promise<number>;
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
    (sceneId: string, play?: boolean) =>
      send('/workbench/lights/scene', {
        scene_id: sceneId,
        ...(play === undefined ? {} : { play }),
      }),
    [send]
  );

  const switchAll = useCallback(
    async (on: boolean, roomIds: readonly string[], lightIds: readonly string[]) => {
      const acts = [
        ...roomIds.map(id => ['/workbench/lights/room', { room_id: id, on }] as const),
        ...lightIds.map(id => ['/workbench/lights/light', { light_id: id, on }] as const),
      ];
      let failed = 0;
      // One after the other: a bridge takes about one room command a second.
      for (const [path, body] of acts) {
        await post(path, body).catch(() => {
          failed += 1;
        });
      }
      await refetch().catch(() => undefined);
      return failed;
    },
    [post, refetch]
  );

  return {
    bridge: query.data,
    loading: query.loading,
    error: query.error,
    refresh: refetch,
    setLight,
    setRoom,
    recallScene,
    switchAll,
  };
}
