import { describe, expect, it } from 'vitest';
import { useMeetingRecorderStore } from '../meetingRecorderStore';

describe('persisted recorder account ownership', () => {
  it('retains same-account recovery and clears foreign recovery before publishing it', () => {
    const store = useMeetingRecorderStore.getState();
    store.setOwner('account-a');
    store.begin(
      {
        meetingId: 'm1',
        startedAt: '2026-09-02T10:00:00Z',
        audioFormat: 'pcm_s16le_16',
        mimeType: null,
        segmentSeconds: 30,
        nextSequence: 1,
      },
      null,
      null
    );
    store.setPhase('interrupted');
    store.setOwner('account-a');
    expect(useMeetingRecorderStore.getState().recording?.meetingId).toBe('m1');
    store.setOwner('account-b');
    expect(useMeetingRecorderStore.getState().recording).toBeNull();
    expect(useMeetingRecorderStore.getState().phase).toBe('idle');
    expect(useMeetingRecorderStore.getState().ownerId).toBe('account-b');
  });
});
