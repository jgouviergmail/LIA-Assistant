/**
 * The recorder lifecycle under fakes: start, segments in order, silence prompt,
 * max duration, stop with missing segments, offline stop, resume, reconcile,
 * processing watch. No browser API is touched.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api-client';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import type { MeetingActionResponse, MeetingDetail, MeetingStartResponse } from '@/types/meetings';

import type { AudioSourceCallbacks, MeetingAudioSource } from '../audio-source';
import { MeetingRecorderController, type RecorderDeps } from '../recorder-controller';
import { SegmentUploader, type SegmentTransport } from '../segment-uploader';

const LIMITS = {
  segment_seconds: 30,
  segment_max_seconds: 60,
  segment_max_bytes: 2_000_000,
  max_duration_minutes: 180,
  silence_prompt_minutes: 10,
};
const ENGINE = {
  provider: 'elevenlabs' as const,
  model: 'scribe_v2',
  diarized: true,
  cost_per_hour_eur: 0.2,
  local_rtf_estimate: null,
};

class FakeSource implements MeetingAudioSource {
  started = false;
  stopped = false;
  constructor(public callbacks: AudioSourceCallbacks) {}
  async start(): Promise<void> {
    this.started = true;
  }
  async stop(): Promise<void> {
    this.stopped = true;
  }
}

function detail(over: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: 'm1',
    status: 'processing',
    stage: 'transcribing',
    started_at: '2026-09-02T10:00:00Z',
    stopped_at: null,
    last_segment_at: null,
    client_timezone: 'Europe/Paris',
    audio_format: 'webm_opus',
    segment_count: 0,
    audio_duration_seconds: null,
    audio_gaps: 0,
    audio_kept_until: null,
    audio_purged_at: null,
    location_lat: null,
    location_lon: null,
    location_label: null,
    calendar_event_id: null,
    stt_provider: null,
    stt_model: null,
    stt_detected_language: null,
    stt_diarized: false,
    stt_cost_eur: null,
    synthesis_model: null,
    synthesis_tokens_in: 0,
    synthesis_tokens_out: 0,
    synthesis_tokens_cache: 0,
    synthesis_cost_eur: null,
    total_cost_eur: null,
    has_transcript: false,
    report: null,
    report_is_edited: false,
    report_edited_at: null,
    template_snapshot: null,
    index_state: null,
    indexed_at: null,
    email_sent_at: null,
    last_error_code: null,
    last_error_message: null,
    template_ref: null,
    template_name: null,
    template_selection: null,
    template_selection_reason: null,
    source_meeting_id: null,
    derived_count: 0,
    transcript: null,
    ...over,
  };
}

interface Harness {
  controller: MeetingRecorderController;
  deps: RecorderDeps;
  sources: FakeSource[];
  puts: number[];
  api: {
    start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
    discard: ReturnType<typeof vi.fn>;
    active: ReturnType<typeof vi.fn>;
    detail: ReturnType<typeof vi.fn>;
  };
  online: { value: boolean };
  clock: { now: number };
  processed: MeetingDetail[];
}

function harness(over: Partial<RecorderDeps> = {}): Harness {
  const sources: FakeSource[] = [];
  const puts: number[] = [];
  const online = { value: true };
  const clock = { now: Date.parse('2026-09-02T10:00:00Z') };
  const processed: MeetingDetail[] = [];
  const transport: SegmentTransport = {
    async put(_id, sequence) {
      puts.push(sequence);
      return { sequence, segment_count: sequence + 1, audio_bytes: 0, status: 'recording' };
    },
  };
  const started: MeetingStartResponse = {
    id: 'm1',
    status: 'recording',
    started_at: '2026-09-02T10:00:00Z',
    engine: ENGINE,
    limits: LIMITS,
  };
  const action: MeetingActionResponse = { id: 'm1', status: 'stopped', stage: null, detail: null };
  const api = {
    start: vi.fn(async () => started),
    stop: vi.fn(async () => action),
    discard: vi.fn(async () => undefined),
    active: vi.fn(async () => null as MeetingDetail | null),
    detail: vi.fn(async () => detail()),
  };
  const deps: RecorderDeps = {
    api,
    getUserMedia: vi.fn(async () => fakeStream()),
    chooseFormat: () => ({ format: 'webm_opus', mimeType: 'audio/webm;codecs=opus' }),
    createSource: (_f, _m, _s, callbacks) => {
      const source = new FakeSource(callbacks);
      sources.push(source);
      return source;
    },
    createUploader: options => new SegmentUploader({ ...options, transport, retryDelaysMs: [10] }),
    position: async () => null,
    acquireWakeLock: async () => null,
    timezone: () => 'Europe/Paris',
    isOnline: () => online.value,
    now: () => clock.now,
    store: useMeetingRecorderStore,
    silenceThresholdRms: 0.01,
    statusPollMs: 1000,
    onProcessed: d => processed.push(d),
    ...over,
  };
  return {
    controller: new MeetingRecorderController(deps),
    deps,
    sources,
    puts,
    api,
    online,
    clock,
    processed,
  };
}

interface FakeTrack {
  onended: (() => void) | null;
  stop: () => void;
}

/** A stream with one audio track whose `onended` the tests can fire. */
function fakeStream(): MediaStream & { track: FakeTrack } {
  const track: FakeTrack = { onended: null, stop: vi.fn() };
  return {
    track,
    getTracks: () => [track],
    getAudioTracks: () => [track],
  } as unknown as MediaStream & { track: FakeTrack };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}

beforeEach(() => {
  vi.useFakeTimers();
  useMeetingRecorderStore.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('MeetingRecorderController.start', () => {
  it('creates the meeting server-side, then opens the capture and records', async () => {
    const h = harness();
    await h.controller.start();
    const state = useMeetingRecorderStore.getState();
    expect(h.api.start).toHaveBeenCalledWith({
      audio_format: 'webm_opus',
      language: 'auto',
      timezone: 'Europe/Paris',
      geolocation: null,
    });
    expect(state.phase).toBe('recording');
    expect(state.recording?.meetingId).toBe('m1');
    expect(state.limits).toEqual(LIMITS);
    expect(h.sources[0].started).toBe(true);
    await h.controller.dispose();
  });

  it('surfaces the server refusal code without opening the microphone', async () => {
    const h = harness();
    h.api.start.mockRejectedValueOnce(
      new ApiError('conflict', 409, { detail: { code: 'no_engine_available' } })
    );
    await h.controller.start();
    expect(useMeetingRecorderStore.getState().phase).toBe('error');
    expect(useMeetingRecorderStore.getState().errorCode).toBe('no_engine_available');
    expect(h.deps.getUserMedia).not.toHaveBeenCalled();
  });

  it('a refused microphone leaves the meeting interrupted, for the user to decide', async () => {
    const h = harness({ getUserMedia: vi.fn(async () => Promise.reject(new Error('denied'))) });
    await h.controller.start();
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('interrupted');
    expect(state.errorCode).toBe('microphone_denied');
    expect(state.recording?.meetingId).toBe('m1');
  });
});

describe('segments and levels', () => {
  it('uploads segments in order and advances the persisted sequence', async () => {
    const h = harness();
    await h.controller.start();
    const source = h.sources[0];
    source.callbacks.onSegment(new Blob(['a']));
    source.callbacks.onSegment(new Blob(['b']));
    await settle();
    expect(h.puts).toEqual([0, 1]);
    expect(useMeetingRecorderStore.getState().recording?.nextSequence).toBe(2);
    expect(useMeetingRecorderStore.getState().uploadedSegments).toBe(2);
    await h.controller.dispose();
  });

  it('asks "still recording?" once after the silence window and re-arms on continue', async () => {
    const h = harness();
    await h.controller.start();
    const source = h.sources[0];
    source.callbacks.onLevel(0);
    h.clock.now += 10 * 60_000;
    source.callbacks.onLevel(0);
    expect(useMeetingRecorderStore.getState().silencePrompt).toBe(true);
    h.controller.continueAfterSilence();
    expect(useMeetingRecorderStore.getState().silencePrompt).toBe(false);
    h.clock.now += 9 * 60_000;
    source.callbacks.onLevel(0);
    expect(useMeetingRecorderStore.getState().silencePrompt).toBe(false);
    await h.controller.dispose();
  });

  it('a microphone track that ends interrupts the capture, keeping the meeting and its queue', async () => {
    const h = harness();
    await h.controller.start();
    const stream = await (h.deps.getUserMedia as ReturnType<typeof vi.fn>).mock.results[0].value;
    h.sources[0].callbacks.onSegment(new Blob(['a']));
    stream.track.onended?.();
    await settle();
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('interrupted');
    expect(state.errorCode).toBe('capture_failed');
    expect(h.sources[0].stopped).toBe(true);
    // The segment already captured still leaves.
    expect(h.puts).toEqual([0]);
    expect(state.recording?.meetingId).toBe('m1');
    await h.controller.dispose();
  });

  it('a fatal upload refusal ends the capture with the server code', async () => {
    const transport: SegmentTransport = {
      async put() {
        throw new ApiError('gone', 409, { detail: { code: 'meeting_not_recording' } });
      },
    };
    const h = harness({
      createUploader: options =>
        new SegmentUploader({ ...options, transport, retryDelaysMs: [10] }),
    });
    await h.controller.start();
    h.sources[0].callbacks.onSegment(new Blob(['a']));
    await settle();
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('error');
    expect(state.errorCode).toBe('meeting_not_recording');
    expect(h.sources[0].stopped).toBe(true);
  });
});

describe('stop', () => {
  it('flushes, declares the uploader count and hands over to processing', async () => {
    const h = harness();
    await h.controller.start();
    h.sources[0].callbacks.onSegment(new Blob(['a']));
    h.sources[0].callbacks.onSegment(new Blob(['b']));
    const outcome = await h.controller.stop();
    expect(outcome).toBe('processing');
    expect(h.api.stop).toHaveBeenCalledWith('m1', { segment_count: 2, allow_gaps: false });
    expect(h.sources[0].stopped).toBe(true);
    expect(useMeetingRecorderStore.getState().phase).toBe('processing');
    await h.controller.dispose();
  });

  it('reports missing segments so the UI can offer to finalize anyway', async () => {
    const h = harness();
    h.api.stop.mockRejectedValueOnce(
      new ApiError('conflict', 409, { detail: { code: 'segments_missing', missing: [3, 4] } })
    );
    await h.controller.start();
    expect(await h.controller.stop()).toBe('missing_segments');
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('interrupted');
    expect(state.missingSegments).toEqual([3, 4]);
    expect(await h.controller.finalizeWithGaps()).toBe('processing');
    expect(h.api.stop).toHaveBeenLastCalledWith('m1', { segment_count: 0, allow_gaps: true });
    await h.controller.dispose();
  });

  it('offline with segments pending closes the capture and waits as interrupted', async () => {
    const h = harness();
    await h.controller.start();
    h.online.value = false;
    h.sources[0].callbacks.onSegment(new Blob(['a']));
    await settle();
    expect(await h.controller.stop()).toBe('offline');
    expect(useMeetingRecorderStore.getState().phase).toBe('interrupted');
    expect(h.api.stop).not.toHaveBeenCalled();
    await h.controller.dispose();
  });

  it('a recording with no audio is discarded rather than left waiting', async () => {
    const h = harness();
    h.api.stop.mockRejectedValueOnce(
      new ApiError('conflict', 409, { detail: { code: 'no_audio' } })
    );
    await h.controller.start();
    expect(await h.controller.stop()).toBe('failed');
    expect(h.api.discard).toHaveBeenCalledWith('m1');
    expect(useMeetingRecorderStore.getState().phase).toBe('idle');
  });

  it('finalizes by itself at the maximum duration', async () => {
    const h = harness();
    await h.controller.start();
    h.clock.now += 181 * 60_000;
    await vi.advanceTimersByTimeAsync(1000);
    await settle();
    expect(h.api.stop).toHaveBeenCalledTimes(1);
    await h.controller.dispose();
  });
});

describe('processing watch and reconcile', () => {
  it('polls the meeting until terminal, then reports and clears the store', async () => {
    const h = harness();
    h.api.detail
      .mockResolvedValueOnce(detail({ status: 'processing' }))
      .mockResolvedValueOnce(detail({ status: 'ready', stage: null }));
    await h.controller.start();
    await h.controller.stop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(useMeetingRecorderStore.getState().phase).toBe('processing');
    await vi.advanceTimersByTimeAsync(1000);
    await settle();
    expect(h.processed.map(d => d.status)).toEqual(['ready']);
    expect(useMeetingRecorderStore.getState().phase).toBe('idle');
  });

  it('adopts a live meeting the server knows as interrupted, and drops a stale one', async () => {
    const h = harness();
    h.api.active.mockResolvedValueOnce(
      detail({
        id: 'm9',
        status: 'interrupted',
        stage: null,
        segment_count: 5,
        audio_format: 'pcm_s16le_16',
      })
    );
    await h.controller.reconcile();
    let state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('interrupted');
    expect(state.recording?.meetingId).toBe('m9');
    expect(state.recording?.nextSequence).toBe(5);

    h.api.active.mockResolvedValueOnce(null);
    await h.controller.reconcile();
    state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('idle');
    expect(state.recording).toBeNull();
  });

  it('resume reopens the capture on the persisted meeting, continuing the sequence', async () => {
    const h = harness();
    h.api.active.mockResolvedValueOnce(
      detail({ status: 'interrupted', stage: null, segment_count: 3 })
    );
    await h.controller.reconcile();
    await h.controller.resume();
    expect(useMeetingRecorderStore.getState().phase).toBe('recording');
    h.sources[0].callbacks.onSegment(new Blob(['x']));
    await settle();
    expect(h.puts).toEqual([3]);
    await h.controller.dispose();
  });

  it('discard deletes the meeting and releases everything', async () => {
    const h = harness();
    await h.controller.start();
    await h.controller.discard();
    expect(h.api.discard).toHaveBeenCalledWith('m1');
    expect(h.sources[0].stopped).toBe(true);
    expect(useMeetingRecorderStore.getState().phase).toBe('idle');
  });
});

describe('edge cases the server decides', () => {
  it('a server-side duration cap finalizes with what the server holds, without a gap', async () => {
    // A throttled tab missed the client-side cap: the server refuses the extra
    // segment with 413. The stop must declare the refused sequence, not the
    // assigned count, or the minutes would report a gap that is not one.
    const puts: number[] = [];
    const transport: SegmentTransport = {
      async put(_id, sequence) {
        if (sequence >= 2) {
          throw new ApiError('cap', 413, {
            detail: { code: 'duration_cap_reached', max_duration_minutes: 180 },
          });
        }
        puts.push(sequence);
        return { sequence, segment_count: sequence + 1, audio_bytes: 0, status: 'recording' };
      },
    };
    const h = harness({
      createUploader: options =>
        new SegmentUploader({ ...options, transport, retryDelaysMs: [10] }),
    });
    await h.controller.start();
    for (let i = 0; i < 3; i++) h.sources[0].callbacks.onSegment(new Blob(['x']));
    await vi.advanceTimersByTimeAsync(50);
    await settle();
    expect(puts).toEqual([0, 1]);
    expect(h.api.stop).toHaveBeenCalledWith('m1', { segment_count: 2, allow_gaps: false });
    expect(useMeetingRecorderStore.getState().phase).toBe('processing');
    expect(h.sources[0].stopped).toBe(true);
    await h.controller.dispose();
  });

  it('resume refuses a container this browser cannot produce and keeps the meeting', async () => {
    const store = useMeetingRecorderStore.getState();
    store.begin(
      {
        meetingId: 'm9',
        startedAt: '2026-09-02T10:00:00Z',
        audioFormat: 'ogg_opus',
        mimeType: null,
        segmentSeconds: 30,
        nextSequence: 4,
      },
      null,
      null
    );
    store.setPhase('interrupted');
    const h = harness(); // this browser chooses WebM
    await h.controller.resume();
    const state = useMeetingRecorderStore.getState();
    expect(state.phase).toBe('interrupted');
    expect(state.errorCode).toBe('format_unavailable');
    expect(state.recording?.meetingId).toBe('m9');
    expect(h.deps.getUserMedia).not.toHaveBeenCalled();
    expect(h.sources).toHaveLength(0);
  });

  it('resume adopts this browser MIME type when the container matches', async () => {
    const store = useMeetingRecorderStore.getState();
    store.begin(
      {
        meetingId: 'm9',
        startedAt: '2026-09-02T10:00:00Z',
        audioFormat: 'webm_opus',
        mimeType: null,
        segmentSeconds: 30,
        nextSequence: 4,
      },
      null,
      null
    );
    store.setPhase('interrupted');
    const mimes: Array<string | undefined> = [];
    const h = harness({
      createSource: (_format, mimeType, _seconds, callbacks) => {
        mimes.push(mimeType);
        return new FakeSource(callbacks);
      },
    });
    await h.controller.resume();
    expect(mimes).toEqual(['audio/webm;codecs=opus']);
    expect(useMeetingRecorderStore.getState().phase).toBe('recording');
    await h.controller.dispose();
  });
});

