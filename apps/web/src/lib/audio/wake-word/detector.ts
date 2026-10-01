/**
 * The page's side of the wake-word detector (ADR-329): one worker, one state.
 *
 * `load(language)` starts (or restarts) the worker on the language's model and
 * resolves once it is ready or known unavailable; `push` hands it 16 kHz int16
 * PCM (the buffer is transferred, not copied); `reset` restarts the stream
 * after a pause in the capture; `dispose` ends the worker. A detection calls
 * `onDetected`, a spoken command `onCommand`. The capture belongs to the caller — the classic voice mode
 * feeds its own, a live session in standby opens one — so the detector never
 * holds a microphone.
 */
import type { Language } from '@/i18n/settings';

import type { WakeCommand } from './commands';
import type { FromWorker, ToWorker, WakeWordFailure } from './protocol';

export type DetectorState = 'idle' | 'loading' | 'ready' | 'unavailable';

/** The slice of `Worker` the detector uses (a fake in tests). */
export interface WorkerLike {
  postMessage(message: ToWorker, transfer?: Transferable[]): void;
  onmessage: ((event: MessageEvent<FromWorker>) => void) | null;
  onerror: ((event: ErrorEvent) => void) | null;
  terminate(): void;
}

export interface WakeWordDetectorOptions {
  onDetected: () => void;
  /** A spoken command was heard (« Stop »); ignored when absent. */
  onCommand?: (command: WakeCommand) => void;
  onStateChange?: (
    state: DetectorState,
    detail: { phrase?: string; failure?: WakeWordFailure }
  ) => void;
  createWorker?: () => WorkerLike;
}

function defaultWorker(): WorkerLike {
  return new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' }) as WorkerLike;
}

export class WakeWordDetector {
  private worker: WorkerLike | null = null;
  private state: DetectorState = 'idle';
  private phraseText: string | null = null;
  private commandList: WakeCommand[] = [];
  /** Settles the pending `load` (with `idle` when disposed before it answered). */
  private settle: ((state: DetectorState) => void) | null = null;

  constructor(private readonly options: WakeWordDetectorOptions) {}

  get currentState(): DetectorState {
    return this.state;
  }

  /** The phrase the loaded model listens for, once ready. */
  get phrase(): string | null {
    return this.phraseText;
  }

  /** The spoken commands the loaded model ships, once ready. */
  get commands(): WakeCommand[] {
    return this.commandList;
  }

  /** Load the language's model; resolves with the state it settled in. */
  load(language: Language): Promise<DetectorState> {
    this.dispose();
    const worker = (this.options.createWorker ?? defaultWorker)();
    this.worker = worker;
    this.setState('loading', {});
    const settled = new Promise<DetectorState>(resolve => {
      this.settle = resolve;
      worker.onmessage = event => {
        if (this.worker !== worker) return;
        const message = event.data;
        if (message.type === 'ready') {
          this.phraseText = message.phrase;
          this.commandList = message.commands;
          this.setState('ready', { phrase: message.phrase });
          resolve('ready');
        } else if (message.type === 'failed') {
          this.setState('unavailable', { failure: message.reason });
          resolve('unavailable');
        } else if (this.state === 'ready') {
          if (message.type === 'command') this.options.onCommand?.(message.command);
          else this.options.onDetected();
        }
      };
      worker.onerror = () => {
        if (this.worker !== worker) return;
        // A worker that cannot even start (a refused script, a CSP) is a
        // runtime the browser does not offer.
        this.setState('unavailable', { failure: 'runtime' });
        resolve('unavailable');
      };
    });
    worker.postMessage({ type: 'load', language });
    return settled;
  }

  /** 16 kHz int16 PCM; transferred to the worker (the caller's buffer is detached). */
  push(pcm16: ArrayBuffer): void {
    if (this.state !== 'ready' || !this.worker) return;
    this.worker.postMessage({ type: 'audio', samples: pcm16 }, [pcm16]);
  }

  /** The capture paused and resumes: no stale audio is glued to the new. */
  reset(): void {
    this.worker?.postMessage({ type: 'reset' });
  }

  dispose(): void {
    this.worker?.terminate();
    this.worker = null;
    this.phraseText = null;
    this.commandList = [];
    this.settle?.('idle');
    this.settle = null;
    if (this.state !== 'idle') this.setState('idle', {});
  }

  private setState(
    state: DetectorState,
    detail: { phrase?: string; failure?: WakeWordFailure }
  ): void {
    this.state = state;
    this.options.onStateChange?.(state, detail);
  }
}
