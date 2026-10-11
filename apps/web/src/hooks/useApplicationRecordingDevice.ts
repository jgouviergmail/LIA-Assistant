'use client';

import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';
import {
  registerRecordingDevice,
  type RecordingDeviceOwner,
} from '@/lib/application-recording-device';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';

/** Register the existing dashboard owner; never instantiate another recorder. */
export function useApplicationRecordingDevice() {
  const { user } = useAuth();
  const recorder = useMeetingRecorderContext();
  const { start, stop, resume, finalizeWithGaps, discard, isSupported } = recorder ?? {};
  useEffect(() => {
    if (!user?.id || !start || !stop || !resume || !finalizeWithGaps || !discard) return;
    const owner: RecordingDeviceOwner = {
      snapshot: () => {
        const state = useMeetingRecorderStore.getState();
        if (state.ownerId !== user.id) return { phase: 'idle', meeting_id: null, supported: false };
        return {
          phase: state.phase,
          meeting_id: state.recording?.meetingId ?? null,
          supported: isSupported === true,
        };
      },
      execute: async action => {
        const commands = { start, stop, resume, finalize_with_gaps: finalizeWithGaps, discard };
        await commands[action]();
      },
    };
    return registerRecordingDevice(user.id, owner);
  }, [user?.id, start, stop, resume, finalizeWithGaps, discard, isSupported]);
}

export function ApplicationRecordingDeviceRegistration() {
  useApplicationRecordingDevice();
  return null;
}
