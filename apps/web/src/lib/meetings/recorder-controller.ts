/**
 * The meeting recorder, as one testable state machine (ADR-258).
 *
 * Everything that touches a browser API or the network is injected
 * (`RecorderDeps`), so the whole lifecycle — start, offline, silence prompt,
 * max duration, stop with missing segments, resume after a reload, processing
 * watch — runs under vitest with fakes. The React side (`useMeetingRecorder`,
 * `MeetingRecorderProvider`) only creates one controller and reads the store.
 *
 * Invariants the controller keeps:
 *  - a capture is never open without a server meeting behind it;
 *  - every segment leaves in sequence order (the uploader) and the count the
 *    stop declares is the uploader's own count, never a guess;
 *  - the microphone is released on every exit path (stop, discard, error).
 */

import type { WakeLockHandle } from '@/lib/wake-lock';
import {
  MEETING_DEFAULT_SEGMENT_SECONDS,
  MEETING_DEFAULT_SILENCE_PROMPT_MINUTES,
} from '@/lib/constants';
import type { AudioFormatChoice } from '@/lib/meetings/audio-format';
import type { AudioSourceCallbacks, MeetingAudioSource } from '@/lib/meetings/audio-source';
import { SilenceWatchdog } from '@/lib/meetings/silence-watchdog';
import type { SegmentUploader, SegmentUploaderOptions } from '@/lib/meetings/segment-uploader';
import { meetingErrorCode, missingSegmentsOf } from '@/lib/meetings/api';
import type {
  MeetingActionResponse,
  MeetingAudioFormat,
  MeetingDetail,
  MeetingGeolocation,
  MeetingStartRequest,
  MeetingStartResponse,
  MeetingStopRequest,
} from '@/types/meetings';
import {
  CAPTURING_PHASES,
  type MeetingRecorderStore,
  type PersistedRecording,
} from '@/stores/meetingRecorderStore';

export interface RecorderApi {
  start: (request: MeetingStartRequest) => Promise<MeetingStartResponse>;
  stop: (id: string, request: MeetingStopRequest) => Promise<MeetingActionResponse>;
  discard: (id: string) => Promise<void>;
  active: () => Promise<MeetingDetail | null>;
  detail: (id: string) => Promise<MeetingDetail>;
}

export interface RecorderDeps {
  api: RecorderApi;
  getUserMedia: () => Promise<MediaStream>;
  chooseFormat: () => AudioFormatChoice;
  createSource: (
    format: MeetingAudioFormat,
    mimeType: string | undefined,
    segmentSeconds: number,
    callbacks: AudioSourceCallbacks
  ) => MeetingAudioSource;
  /** The transport is the deps' business: production binds the API, tests a fake. */
  createUploader: (options: Omit<SegmentUploaderOptions, 'transport'>) => SegmentUploader;
  position: () => Promise<MeetingGeolocation | null>;
  acquireWakeLock: () => Promise<WakeLockHandle | null>;
  timezone: () => string;
  isOnline: () => boolean;
  now: () => number;
  /** Store accessors (zustand `getState`/`setState` shape). */
  store: { getState: () => MeetingRecorderStore };
  /** Level under which the watchdog counts silence. */
  silenceThresholdRms: number;
  /** Detail polling cadence while processing. */
  statusPollMs: number;
  /** Fires when a watched meeting reaches `ready` or `failed`. */
  onProcessed?: (detail: MeetingDetail) => void;
}

export type StopOutcome = 'processing' | 'missing_segments' | 'offline' | 'failed';

export class MeetingRecorderController {
  private stream: MediaStream | null = null;
  private source: MeetingAudioSource | null = null;
  private uploader: SegmentUploader | null = null;
  private wakeLock: WakeLockHandle | null = null;
  private watchdog: SilenceWatchdog | null = null;
  private tickTimer: ReturnType<typeof setInterval> | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private onlineListener: (() => void) | null = null;
  private offlineListener: (() => void) | null = null;
  private stopping = false;
  private onProcessedCallback: ((detail: MeetingDetail) => void) | null = null;

  constructor(private readonly deps: RecorderDeps) {}

  /** Replace the completion listener (React re-binds it on every render it changes). */
  setOnProcessed(callback: ((detail: MeetingDetail) => void) | null): void {
    this.onProcessedCallback = callback;
  }

  private get store(): MeetingRecorderStore {
    return this.deps.store.getState();
  }

  // ------------------------------------------------------------------ start

  /** Open a recording: server first, then the microphone. */
  async start(): Promise<void> {
    const store = this.store;
    if (store.phase !== 'idle' && store.phase !== 'error') return;
    store.reset();
    store.setPhase('starting');
    const choice = this.deps.chooseFormat();
    let started: MeetingStartResponse;
    try {
      started = await this.deps.api.start({
        audio_format: choice.format,
        language: 'auto',
        timezone: this.deps.timezone(),
        geolocation: await this.deps.position(),
      });
    } catch (error) {
      store.fail(meetingErrorCode(error) ?? 'start_failed');
      return;
    }
    const recording: PersistedRecording = {
      meetingId: started.id,
      startedAt: started.started_at,
      audioFormat: choice.format,
      mimeType: choice.mimeType ?? null,
      segmentSeconds: started.limits.segment_seconds,
      nextSequence: 0,
    };
    store.begin(recording, started.engine, started.limits);
    await this.openCapture(recording, started.limits.silence_prompt_minutes);
  }

  /** Continue a recording this page did not capture (reload, microphone lost). */
  async resume(): Promise<void> {
    const store = this.store;
    const recording = store.recording;
    if (!recording || store.phase !== 'interrupted') return;
    const capture = this.captureFor(recording);
    if (capture === null) {
      // Started elsewhere in a container this browser cannot produce: the
      // segments of one meeting must stay homogeneous, so from here the user
      // can only finalize or discard.
      store.fail('format_unavailable');
      store.setPhase('interrupted');
      return;
    }
    store.setPhase('recording');
    const minutes =
      store.limits?.silence_prompt_minutes ?? MEETING_DEFAULT_SILENCE_PROMPT_MINUTES;
    await this.openCapture(capture, minutes);
  }

  /**
   * The recording with a MIME type this browser can honour, or null.
   *
   * PCM is container-free and works everywhere. An Opus recording adopted from
   * another device carries no MIME type; it can continue only where this
   * browser's own choice is the same container.
   */
  private captureFor(recording: PersistedRecording): PersistedRecording | null {
    if (recording.audioFormat === 'pcm_s16le_16' || recording.mimeType) return recording;
    const choice = this.deps.chooseFormat();
    if (choice.format !== recording.audioFormat || !choice.mimeType) return null;
    return { ...recording, mimeType: choice.mimeType };
  }

  private async openCapture(
    recording: PersistedRecording,
    silencePromptMinutes: number
  ): Promise<void> {
    const store = this.store;
    let stream: MediaStream;
    try {
      stream = await this.deps.getUserMedia();
    } catch {
      // The meeting exists but nothing captures: the user chooses what to do
      // (resume once the microphone is allowed, finalize, discard). `fail`
      // records the code; the phase stays interrupted, not error.
      store.fail('microphone_denied');
      store.setPhase('interrupted');
      return;
    }
    this.stream = stream;
    // An incoming call, a headset change or a revoked permission ends the
    // track: the capture closes and the meeting waits as `interrupted` — the
    // queued segments keep leaving, and the user resumes with one tap.
    for (const track of stream.getAudioTracks()) {
      track.onended = () => {
        void this.interruptCapture('capture_failed');
      };
    }
    this.watchdog = new SilenceWatchdog({
      thresholdRms: this.deps.silenceThresholdRms,
      promptAfterMs: silencePromptMinutes * 60_000,
    });
    this.uploader = this.deps.createUploader({
      meetingId: recording.meetingId,
      startSequence: recording.nextSequence,
      isOnline: this.deps.isOnline,
      onProgress: progress => {
        this.store.setProgress(progress.uploaded, progress.pending);
      },
      onFatal: code => {
        // The cap is a stop, not a failure: the server keeps every segment
        // before it, so the minutes are built from what exists.
        if (code === 'duration_cap_reached') void this.stop({ reason: 'max_duration' });
        else void this.abortCapture(code);
      },
    });
    this.source = this.deps.createSource(
      recording.audioFormat,
      recording.mimeType ?? undefined,
      recording.segmentSeconds,
      {
        onSegment: blob => this.onSegment(blob),
        onLevel: rms => this.onLevel(rms),
        onError: () => {
          void this.abortCapture('capture_failed');
        },
      }
    );
    try {
      await this.source.start(stream);
    } catch {
      await this.releaseCapture();
      store.setPhase('interrupted');
      return;
    }
    this.wakeLock = await this.deps.acquireWakeLock();
    this.installOnlineListeners();
    this.startTicker();
    store.setPhase(this.deps.isOnline() ? 'recording' : 'offline');
  }

  // -------------------------------------------------------------- capture

  private onSegment(blob: Blob): void {
    const uploader = this.uploader;
    if (!uploader) return;
    uploader.enqueue(blob);
    this.store.setNextSequence(uploader.sequenceCount);
  }

  private onLevel(rms: number): void {
    const store = this.store;
    store.setLevel(rms);
    const verdict = this.watchdog?.feed(rms, this.deps.now());
    if (verdict === 'prompt') store.setSilencePrompt(true);
  }

  /** The user answered the silence prompt with "continue". */
  continueAfterSilence(): void {
    this.watchdog?.acknowledge(this.deps.now());
    this.store.setSilencePrompt(false);
  }

  private startTicker(): void {
    this.stopTicker();
    this.tickTimer = setInterval(() => this.tick(), 1000);
    this.tick();
  }

  private stopTicker(): void {
    if (this.tickTimer !== null) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
  }

  private tick(): void {
    const store = this.store;
    const recording = store.recording;
    if (!recording) return;
    const elapsed = Math.max(
      0,
      Math.floor((this.deps.now() - Date.parse(recording.startedAt)) / 1000)
    );
    store.setElapsed(elapsed);
    const maxMinutes = store.limits?.max_duration_minutes;
    if (maxMinutes && elapsed >= maxMinutes * 60 && !this.stopping) {
      // The server refuses anything beyond the cap: finalize what exists.
      void this.stop({ allowGaps: false, reason: 'max_duration' });
    }
  }

  private installOnlineListeners(): void {
    if (typeof window === 'undefined') return;
    this.onlineListener = () => {
      if (this.store.phase === 'offline') this.store.setPhase('recording');
    };
    this.offlineListener = () => {
      if (this.store.phase === 'recording') this.store.setPhase('offline');
    };
    window.addEventListener('online', this.onlineListener);
    window.addEventListener('offline', this.offlineListener);
  }

  private removeOnlineListeners(): void {
    if (typeof window === 'undefined') return;
    if (this.onlineListener) window.removeEventListener('online', this.onlineListener);
    if (this.offlineListener) window.removeEventListener('offline', this.offlineListener);
    this.onlineListener = null;
    this.offlineListener = null;
  }

  /** Release the microphone and every capture resource; the meeting itself is untouched. */
  private async releaseCapture(): Promise<void> {
    this.stopTicker();
    this.removeOnlineListeners();
    const source = this.source;
    this.source = null;
    if (source) await source.stop().catch(() => undefined);
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    if (this.wakeLock) {
      await this.wakeLock.release().catch(() => undefined);
      this.wakeLock = null;
    }
    this.watchdog = null;
    this.store.setLevel(0);
  }

  /** Close the capture but keep the meeting and its queue: the user decides. */
  private async interruptCapture(code: string): Promise<void> {
    if (this.stopping || !CAPTURING_PHASES.includes(this.store.phase)) return;
    await this.releaseCapture();
    this.store.fail(code);
    this.store.setPhase('interrupted');
  }

  private async abortCapture(code: string): Promise<void> {
    await this.releaseCapture();
    this.uploader?.dispose();
    this.uploader = null;
    this.store.fail(code);
  }

  // ------------------------------------------------------------------ stop

  /**
   * Stop capturing, flush the segments, hand the meeting to processing.
   *
   * `missing_segments` means the server never received some sequences (a
   * previous page died with segments in flight): the UI offers to finalize
   * anyway (`allowGaps`) or to discard. `offline` means the last segments
   * cannot leave yet: the capture is closed, the meeting waits as `interrupted`.
   */
  async stop(
    options: { allowGaps?: boolean; reason?: 'user' | 'max_duration' } = {}
  ): Promise<StopOutcome> {
    const store = this.store;
    const recording = store.recording;
    if (!recording || this.stopping) return 'failed';
    this.stopping = true;
    store.setPhase('stopping');
    store.setSilencePrompt(false);
    try {
      await this.releaseCapture();
      if (!(await this.flushUploads())) {
        store.setPhase('interrupted');
        return 'offline';
      }
      return await this.submitStop(recording.meetingId, options.allowGaps ?? false);
    } finally {
      this.stopping = false;
    }
  }

  /**
   * Drain the queue; false when the connection is down and segments remain.
   *
   * A queue the server refused for good is settled: what it holds can never
   * leave, and the count declared is what the server actually received.
   */
  private async flushUploads(): Promise<boolean> {
    const uploader = this.uploader;
    if (!uploader) return true;
    if (uploader.fatalCode === null && !this.deps.isOnline() && uploader.pendingCount > 0) {
      return false;
    }
    await uploader.flush();
    this.store.setNextSequence(uploader.settledSequenceCount);
    return uploader.fatalCode !== null || uploader.pendingCount === 0;
  }

  /** The stop request itself, with the server's refusals mapped to outcomes. */
  private async submitStop(meetingId: string, allowGaps: boolean): Promise<StopOutcome> {
    const store = this.store;
    const segmentCount = store.recording?.nextSequence ?? 0;
    try {
      await this.deps.api.stop(meetingId, { segment_count: segmentCount, allow_gaps: allowGaps });
    } catch (error) {
      return this.handleStopRefusal(meetingId, error);
    }
    this.uploader?.dispose();
    this.uploader = null;
    store.setMissingSegments(null);
    store.setPhase('processing');
    this.watchProcessing(meetingId);
    return 'processing';
  }

  private async handleStopRefusal(meetingId: string, error: unknown): Promise<StopOutcome> {
    const store = this.store;
    const code = meetingErrorCode(error);
    if (code === 'segments_missing') {
      store.setMissingSegments(missingSegmentsOf(error) ?? []);
      store.setPhase('interrupted');
      return 'missing_segments';
    }
    if (code === 'no_audio') {
      // Nothing was ever captured: there are no minutes to wait for.
      await this.deps.api.discard(meetingId).catch(() => undefined);
      store.reset();
      return 'failed';
    }
    store.fail(code ?? 'stop_failed');
    return 'failed';
  }

  /** Finalize with the gaps the server reported. */
  finalizeWithGaps(): Promise<StopOutcome> {
    return this.stop({ allowGaps: true });
  }

  /** Delete the meeting and everything captured. */
  async discard(): Promise<void> {
    const store = this.store;
    const recording = store.recording;
    await this.releaseCapture();
    this.uploader?.dispose();
    this.uploader = null;
    this.stopPolling();
    if (recording) await this.deps.api.discard(recording.meetingId).catch(() => undefined);
    store.reset();
  }

  /** Leave an `error`/`processing` phase without touching the server. */
  dismiss(): void {
    this.stopPolling();
    this.store.reset();
  }

  // ------------------------------------------------------------ processing

  private watchProcessing(meetingId: string): void {
    this.stopPolling();
    const poll = async () => {
      let detail: MeetingDetail;
      try {
        detail = await this.deps.api.detail(meetingId);
      } catch {
        this.pollTimer = setTimeout(poll, this.deps.statusPollMs);
        return;
      }
      if (detail.status === 'ready' || detail.status === 'failed') {
        this.pollTimer = null;
        (this.onProcessedCallback ?? this.deps.onProcessed)?.(detail);
        if (this.store.recording?.meetingId === meetingId) this.store.reset();
        return;
      }
      this.pollTimer = setTimeout(poll, this.deps.statusPollMs);
    };
    this.pollTimer = setTimeout(poll, this.deps.statusPollMs);
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  // ------------------------------------------------------------- reconcile

  /**
   * On mount: make the persisted state agree with the server.
   *
   * A persisted `interrupted` recording the server no longer knows is dropped;
   * a live meeting the server knows but this page never saw is adopted (the
   * user started it on another device — they can finalize or discard here).
   */
  async reconcile(): Promise<void> {
    const store = this.store;
    if (store.phase === 'processing' && store.recording) {
      this.watchProcessing(store.recording.meetingId);
      return;
    }
    let live: MeetingDetail | null;
    try {
      live = await this.deps.api.active();
    } catch {
      return;
    }
    if (live === null) {
      if (store.phase === 'interrupted') store.reset();
      return;
    }
    if (store.recording?.meetingId !== live.id) {
      store.begin(
        {
          meetingId: live.id,
          startedAt: live.started_at,
          audioFormat: live.audio_format,
          mimeType: null,
          segmentSeconds: store.limits?.segment_seconds ?? MEETING_DEFAULT_SEGMENT_SECONDS,
          nextSequence: live.segment_count,
        },
        null,
        null
      );
    } else {
      store.setNextSequence(Math.max(store.recording.nextSequence, live.segment_count));
    }
    store.setPhase('interrupted');
  }

  /** Release everything on unmount; the meeting stays as it is server-side. */
  async dispose(): Promise<void> {
    await this.releaseCapture();
    this.uploader?.dispose();
    this.uploader = null;
    this.stopPolling();
  }
}
