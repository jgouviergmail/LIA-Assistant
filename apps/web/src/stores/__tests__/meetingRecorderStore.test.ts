/**
 * What a reload may believe: a capture never survives a page, processing does.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { phaseAfterReload, useMeetingRecorderStore } from '../meetingRecorderStore';

describe('phaseAfterReload', () => {
  it.each([
    ['idle', 'idle'],
    ['starting', 'interrupted'],
    ['recording', 'interrupted'],
    ['offline', 'interrupted'],
    ['interrupted', 'interrupted'],
    ['stopping', 'interrupted'],
    ['processing', 'processing'],
    ['error', 'idle'],
  ] as const)('%s → %s', (phase, expected) => {
    expect(phaseAfterReload(phase)).toBe(expected);
  });
});

describe('meetingRecorderStore', () => {
  beforeEach(() => {
    useMeetingRecorderStore.getState().reset();
  });

  it('begin opens a recording and clears any previous error', () => {
    const store = useMeetingRecorderStore.getState();
    store.fail('start_failed');
    store.begin(
      {
        meetingId: 'm1',
        startedAt: '2026-09-02T10:00:00Z',
        audioFormat: 'webm_opus',
        mimeType: 'audio/webm;codecs=opus',
        segmentSeconds: 30,
        nextSequence: 0,
      },
      null,
      null
    );
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('recording');
    expect(state.errorCode).toBeNull();
    expect(state.recording?.meetingId).toBe('m1');
  });

  it('setNextSequence updates the persisted recording only', () => {
    const store = useMeetingRecorderStore.getState();
    store.setNextSequence(4);
    expect(useMeetingRecorderStore.getState().recording).toBeNull();
    store.begin(
      {
        meetingId: 'm1',
        startedAt: '2026-09-02T10:00:00Z',
        audioFormat: 'pcm_s16le_16',
        mimeType: null,
        segmentSeconds: 30,
        nextSequence: 0,
      },
      null,
      null
    );
    useMeetingRecorderStore.getState().setNextSequence(4);
    expect(useMeetingRecorderStore.getState().recording?.nextSequence).toBe(4);
  });

  it('setTemplateRef remembers the chosen format on the recording only (ADR-259)', () => {
    const store = useMeetingRecorderStore.getState();
    store.setTemplateRef('builtin:daily_standup');
    expect(useMeetingRecorderStore.getState().recording).toBeNull();
    store.begin(
      {
        meetingId: 'm1',
        startedAt: '2026-09-02T10:00:00Z',
        audioFormat: 'pcm_s16le_16',
        mimeType: null,
        segmentSeconds: 30,
        nextSequence: 0,
      },
      null,
      null
    );
    useMeetingRecorderStore.getState().setTemplateRef('builtin:daily_standup');
    expect(useMeetingRecorderStore.getState().recording?.templateRef).toBe('builtin:daily_standup');
    useMeetingRecorderStore.getState().setTemplateRef(null);
    expect(useMeetingRecorderStore.getState().recording?.templateRef).toBeNull();
  });

  it('fail moves to error, drops the silence prompt and zeroes the level', () => {
    const store = useMeetingRecorderStore.getState();
    store.setSilencePrompt(true);
    store.setLevel(0.4);
    store.fail('microphone_denied');
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('error');
    expect(state.errorCode).toBe('microphone_denied');
    expect(state.silencePrompt).toBe(false);
    expect(state.level).toBe(0);
  });
});
