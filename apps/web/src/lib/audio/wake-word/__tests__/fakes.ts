/** Test doubles shared by the wake-word suites. */
import type { MicCapture, MicCaptureOptions } from '@/lib/live/mic-capture';

import type { WorkerLike } from '../detector';
import type { FromWorker, ToWorker } from '../protocol';

/** A worker that records what it is sent and answers when told to. */
export class FakeWorker implements WorkerLike {
  readonly posted: Array<{ message: ToWorker; transfer?: Transferable[] }> = [];
  onmessage: ((event: MessageEvent<FromWorker>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  terminated = false;

  postMessage(message: ToWorker, transfer?: Transferable[]): void {
    this.posted.push({ message, transfer });
  }

  terminate(): void {
    this.terminated = true;
  }

  answer(message: FromWorker): void {
    this.onmessage?.({ data: message } as MessageEvent<FromWorker>);
  }
}

/** A microphone capture whose chunks the test emits, and whose fate it reads. */
export class FakeCapture implements MicCapture {
  readonly stream = { id: 'stream' } as unknown as MediaStream;
  stopped = false;
  detached = false;

  constructor(readonly options: MicCaptureOptions) {}

  emit(samples = 1280): ArrayBuffer {
    const buffer = new Int16Array(samples).buffer;
    this.options.onChunk(buffer);
    return buffer;
  }

  mute(): void {}

  async stop(): Promise<void> {
    this.stopped = true;
  }

  async detach(): Promise<MediaStream | null> {
    if (this.stopped || this.detached) return null;
    this.detached = true;
    return this.stream;
  }
}
