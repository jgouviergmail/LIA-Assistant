import { describe, expect, it, vi } from 'vitest';
import {
  executeRecordingDeviceCommand,
  registerRecordingDevice,
  recordingDeviceSnapshot,
} from '../application-recording-device';
import type { RecordingDeviceOwner } from '../application-recording-device';

const actor = '11111111-1111-4111-8111-111111111111';
const meeting = '22222222-2222-4222-8222-222222222222';

function owner(): RecordingDeviceOwner {
  let state = { phase: 'idle' as const, meeting_id: null as string | null, supported: true };
  return {
    snapshot: () => state,
    execute: vi.fn(async () => {
      state = { ...state, meeting_id: meeting };
    }),
  };
}

describe('addressed original recorder dispatch', () => {
  it('withholds malformed persisted observations so they cannot break the chat request', () => {
    const recorder = owner();
    recorder.snapshot = () => ({
      phase: 'recording',
      meeting_id: 'corrupt-cache-id',
      supported: true,
    });
    const withdraw = registerRecordingDevice(actor, recorder);
    try {
      expect(recordingDeviceSnapshot(actor)).toBeUndefined();
    } finally {
      withdraw();
    }
  });
  it('publishes only the current account observation and withdraws the owner', () => {
    const recorder = owner();
    const withdraw = registerRecordingDevice(actor, recorder);
    expect(recordingDeviceSnapshot(actor)?.actor_id).toBe(actor);
    expect(recordingDeviceSnapshot(meeting)).toBeUndefined();
    withdraw();
    expect(recordingDeviceSnapshot(actor)).toBeUndefined();
  });

  it('refuses foreign accounts, changed state and replay before calling the owner', async () => {
    const recorder = owner();
    const withdraw = registerRecordingDevice(actor, recorder);
    const command = {
      command_id: '33333333-3333-4333-8333-333333333333',
      claim_token: '44444444-4444-4444-8444-444444444444',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      intent: { action: 'start' as const, phase: 'idle' as const, meeting_id: null },
    };
    const stale = await executeRecordingDeviceCommand(meeting, command);
    expect(stale.result).toBe('refused');
    expect(recorder.execute).not.toHaveBeenCalled();
    await executeRecordingDeviceCommand(actor, command);
    await executeRecordingDeviceCommand(actor, command);
    expect(recorder.execute).toHaveBeenCalledTimes(1);
    withdraw();
  });

  it('keeps an uncertain device effect uncertain and never retries it', async () => {
    const recorder = owner();
    recorder.execute = vi.fn(async () => {
      throw new Error('lost reply');
    });
    const withdraw = registerRecordingDevice(actor, recorder);
    const command = {
      command_id: '55555555-5555-4555-8555-555555555555',
      claim_token: '44444444-4444-4444-8444-444444444444',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      intent: { action: 'start' as const, phase: 'idle' as const, meeting_id: null },
    };
    expect((await executeRecordingDeviceCommand(actor, command)).result).toBe('unknown');
    expect((await executeRecordingDeviceCommand(actor, command)).result).toBe('refused');
    expect(recorder.execute).toHaveBeenCalledTimes(1);
    withdraw();
  });
});
