/**
 * The wake word listening on its own microphone (ADR-329): one capture at the
 * engine's rate (16 kHz, 80 ms chunks, through the shared PCM worklet), fed to
 * one detector. The classic voice mode and a live session in standby both
 * listen through it.
 *
 * The model is loaded BEFORE the microphone opens, and a language without a
 * usable model never lights the microphone: the caller falls back to its
 * button. `pause` releases the microphone and keeps the model; `handOff`
 * releases the capture but gives its LIVE stream to the caller (the recording
 * that follows a detection starts without a second permission round trip).
 * Calls are serialised, so a pause asked during a load runs after it, and
 * `dispose` wins over a load in flight. A detection — of the phrase or of a
 * spoken command — reaches the caller only while listening AND while the
 * caller's latest call asked to listen: one that lands between a `pause()` and
 * its turn in the queue is dropped.
 */
import type { Language } from '@/i18n/settings';
import { startMicCapture, type MicCapture, type MicCaptureOptions } from '@/lib/live/mic-capture';
import { logger } from '@/lib/logger';

import type { WakeCommand } from './commands';
import { WakeWordDetector, type WorkerLike } from './detector';
import { CHUNK_SAMPLES, SAMPLE_RATE } from './engine';

export type WakeListenerState = 'idle' | 'loading' | 'listening' | 'unavailable';

export interface WakeListenerOptions {
  onDetected: () => void;
  /** A spoken command was heard (« Stop »); ignored when absent. */
  onCommand?: (command: WakeCommand) => void;
  onStateChange?: (state: WakeListenerState) => void;
  /** The detector's worker (a fake in tests). */
  createWorker?: () => WorkerLike;
  /** Opens the microphone (`startMicCapture` by default; a fake in tests). */
  openCapture?: (options: MicCaptureOptions) => Promise<MicCapture>;
}

export class WakeListener {
  private readonly detector: WakeWordDetector;
  private capture: MicCapture | null = null;
  private language: Language | null = null;
  private state: WakeListenerState = 'idle';
  private disposed = false;
  /** The caller's latest intent, set synchronously by every call. */
  private wanted: 'listen' | 'rest' = 'rest';
  private queue: Promise<unknown> = Promise.resolve();

  constructor(private readonly options: WakeListenerOptions) {
    this.detector = new WakeWordDetector({
      onDetected: () => {
        if (this.heard()) options.onDetected();
      },
      onCommand: command => {
        if (this.heard()) options.onCommand?.(command);
      },
      // The runtime can fail while listening (a WASM trap, a crashed worker):
      // the microphone is released and the caller told, never left listening
      // to a detector that no longer detects.
      onStateChange: state => {
        if (state !== 'unavailable' || this.state !== 'listening') return;
        this.setState('unavailable');
        void this.serialised(() => this.close(false));
      },
      createWorker: options.createWorker,
    });
  }

  get currentState(): WakeListenerState {
    return this.state;
  }

  /** The phrase the loaded model listens for (null until a model is ready). */
  get phrase(): string | null {
    return this.detector.phrase;
  }

  /** The spoken commands the loaded model ships (none until a model is ready). */
  get commands(): WakeCommand[] {
    return this.detector.commands;
  }

  /**
   * Listen for the language's phrase. Resolves with the state reached; rejects
   * with the browser's error when the microphone is refused.
   */
  listen(language: Language): Promise<WakeListenerState> {
    this.wanted = 'listen';
    return this.serialised(() => this.open(language));
  }

  /** Release the microphone; the model stays loaded for the next `listen`. */
  pause(): Promise<void> {
    this.wanted = 'rest';
    return this.serialised(async () => {
      await this.close(false);
    });
  }

  /** Release the capture and give its live stream to the caller (null if none). */
  handOff(): Promise<MediaStream | null> {
    this.wanted = 'rest';
    return this.serialised(() => this.close(true));
  }

  dispose(): Promise<void> {
    this.disposed = true;
    this.wanted = 'rest';
    // Settles a load in flight at once: the queued close below then finds
    // nothing left to open.
    this.detector.dispose();
    return this.serialised(async () => {
      await this.close(false);
      this.setState('idle');
    });
  }

  private async open(language: Language): Promise<WakeListenerState> {
    if (this.disposed) return 'idle';
    if (this.language !== language || this.detector.currentState !== 'ready') {
      this.language = language;
      this.setState('loading');
      const settled = await this.detector.load(language);
      if (settled !== 'ready') {
        await this.close(false);
        this.setState(this.disposed ? 'idle' : 'unavailable');
        return this.state;
      }
    }
    if (!this.capture) {
      try {
        this.capture = await (this.options.openCapture ?? startMicCapture)({
          sampleRate: SAMPLE_RATE,
          chunkSamples: CHUNK_SAMPLES,
          onChunk: pcm16 => this.detector.push(pcm16),
        });
      } catch (error) {
        this.setState('idle');
        throw error;
      }
    }
    this.setState('listening');
    return 'listening';
  }

  private async close(handOff: boolean): Promise<MediaStream | null> {
    // Before any await: a detection still in flight is no longer reported.
    if (this.state === 'listening') this.setState('idle');
    const capture = this.capture;
    this.capture = null;
    if (!capture) return null;
    this.detector.reset();
    if (handOff) return capture.detach();
    try {
      await capture.stop();
    } catch (error) {
      // A context the browser already closed: the tracks are released first,
      // so the microphone is off whatever this says.
      logger.warn('wake_listener_capture_release_failed', {
        component: 'WakeListener',
        error: error instanceof Error ? error.name : 'unknown',
      });
    }
    return null;
  }

  /** Whether a detection arriving now is reported: listening, and still asked to. */
  private heard(): boolean {
    return this.state === 'listening' && this.wanted === 'listen';
  }

  private serialised<T>(operation: () => Promise<T>): Promise<T> {
    const run = this.queue.then(operation);
    // A failed call must not poison the next: it waits on the settled chain.
    this.queue = run.catch(() => undefined);
    return run;
  }

  private setState(state: WakeListenerState): void {
    if (this.state === state) return;
    this.state = state;
    this.options.onStateChange?.(state);
  }
}
