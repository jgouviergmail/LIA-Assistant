'use client';
/** The late-bound private target remains local and revalidated at activation. */
import { useCallback, useEffect, useRef, type RefObject } from 'react';
import type { WorldPrivateSignalsControl } from './useWorldPrivateSignals';
import type { WorldFunctionHandle } from './WorldFunctionControls';
import type { WorldDeviceHandle } from './WorldDeviceControls';
import { sceneActivity } from './scene-activities';
export function useWorldSignalHost(
  control: WorldPrivateSignalsControl,
  functions: RefObject<WorldFunctionHandle | null>,
  devices: RefObject<WorldDeviceHandle | null>
) {
  const current = useRef(control);
  useEffect(() => {
    current.current = control;
  }, [control]);
  return useCallback(
    (propId: string): boolean | null => {
      const signal = current.current.signals.find(item => item.propId === propId);
      if (!signal) return null;
      const target = signal.target;
      if (!target) {
        const activity = sceneActivity(propId);
        return activity ? (functions.current?.openScene(activity) ?? false) : false;
      }
      if (target.kind === 'notice') return devices.current?.openNotice(target.noticeKey) ?? false;
      if (target.kind === 'gallery') {
        const opened = functions.current?.openDestination(target) ?? false;
        if (opened) current.current.acknowledge(propId);
        return opened;
      }
      return (
        functions.current?.openDestination({
          kind: 'workboard',
          filters: {},
          ticketId: target.ticketId,
        }) ?? false
      );
    },
    [functions, devices]
  );
}
