/**
 * A gapless player for the provider's raw PCM stream (ADR-299, spec §1.5).
 *
 * ONE `AudioWorkletNode` reads a queue of chunks continuously, resampling
 * from the chunk's rate to the context's with linear interpolation ACROSS
 * chunk boundaries — the graph never sees a chunk start. The previous shape
 * (one `AudioBufferSourceNode` per chunk scheduled on the context clock) is
 * exactly the pattern Chrome 152 (152.0.7977.83, measured on the owner's
 * workstation 2026-09-19) sometimes renders with the start of a chunk replaced
 * by one 128-sample render block repeated ~100 times — a « biiiip » of a
 * quarter second, reported by the owner on every session and by others on
 * AI Studio (discuss.ai.google.dev 180487, 181671). The raw provider audio
 * and a Chromium 148 rendering are clean; the worklet removes the chunk
 * scheduling the defect needs, and the per-chunk resampling with it.
 *
 * `AudioQueue` decodes ENCODED chunks through `decodeAudioData`; a live
 * stream is raw 16-bit PCM arriving every few tens of milliseconds, and an
 * interruption must empty the queue at once (`flush()`, handled inside the
 * worklet so nothing already handed over plays on). The iOS rules AudioQueue
 * learned still apply: the context is created and resumed on a user gesture
 * (`warmup`), never lazily on the first chunk. The worklet says when it
 * DRAINED (exactly, on the render thread) so `isSpeaking` needs no timer; a
 * drain report older than the last chunk handed over is ignored, because a
 * chunk can be posted while the report of the previous silence is in flight.
 *
 * The processor runs inside the AudioWorklet global scope, so it is shipped
 * as a string turned into a Blob URL (the CSP allows `blob:` worklets — see
 * `lib/csp.ts`), like the microphone's `lib/audio/pcm-worklet.ts`.
 */

type SpeakingListener = (speaking: boolean) => void;

/** Name registered with `registerProcessor`; the node is created with it. */
export const PCM_PLAYER_PROCESSOR_NAME = 'lia-pcm-stream-player';

/** What the main thread posts to the worklet. */
export type PcmPlayerCommand =
  | { type: 'chunk'; seq: number; rate: number; samples: Float32Array }
  | { type: 'flush' };

/** What the worklet posts back: the queue ran dry after chunk `seq`. */
export interface PcmPlayerDrained {
  type: 'drained';
  seq: number;
}

/**
 * Source of the worklet module: a queue of chunks read continuously at the
 * context's rate, linearly interpolated, a `drained` report when it empties.
 *
 * @returns JavaScript source of the worklet module.
 */
export function buildPcmPlayerWorkletSource(): string {
  return `
    class LiaPcmStreamPlayer extends AudioWorkletProcessor {
      constructor() {
        super();
        this.queue = [];
        this.position = 0;
        this.lastSeq = -1;
        this.playing = false;
        this.port.onmessage = (event) => {
          const message = event.data;
          if (message.type === 'chunk') {
            this.queue.push({ samples: message.samples, rate: message.rate, seq: message.seq });
          } else if (message.type === 'flush') {
            this.queue.length = 0;
            this.position = 0;
            this.playing = false;
          }
        };
      }

      dropConsumed() {
        while (this.queue.length > 0 && this.position >= this.queue[0].samples.length) {
          this.position -= this.queue[0].samples.length;
          this.lastSeq = this.queue[0].seq;
          this.queue.shift();
        }
      }

      process(inputs, outputs) {
        const output = outputs[0][0];
        if (!output) return true;
        for (let i = 0; i < output.length; i++) {
          this.dropConsumed();
          if (this.queue.length === 0) {
            output[i] = 0;
            continue;
          }
          const head = this.queue[0];
          const index = Math.floor(this.position);
          const fraction = this.position - index;
          const a = head.samples[index];
          let b;
          if (index + 1 < head.samples.length) b = head.samples[index + 1];
          else if (this.queue.length > 1) b = this.queue[1].samples[0];
          else b = a;
          output[i] = a + (b - a) * fraction;
          this.position += head.rate / sampleRate;
          this.playing = true;
        }
        this.dropConsumed();
        if (this.playing && this.queue.length === 0) {
          this.playing = false;
          this.position = 0;
          this.port.postMessage({ type: 'drained', seq: this.lastSeq });
        }
        return true;
      }
    }

    registerProcessor('${PCM_PLAYER_PROCESSOR_NAME}', LiaPcmStreamPlayer);
  `;
}

let workletUrl: string | null = null;

/** Blob URL of the worklet module, created once per page. */
export function getPcmPlayerWorkletUrl(): string {
  if (workletUrl) return workletUrl;
  const blob = new Blob([buildPcmPlayerWorkletSource()], { type: 'application/javascript' });
  workletUrl = URL.createObjectURL(blob);
  return workletUrl;
}

export class PcmStreamPlayer {
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private speaking = false;
  private listener: SpeakingListener | null = null;
  private seq = 0;

  get isSpeaking(): boolean {
    return this.speaking;
  }

  onSpeakingChange(listener: SpeakingListener): void {
    this.listener = listener;
  }

  /** Create or resume the context and load the worklet — call from a user gesture (iOS). */
  async warmup(): Promise<void> {
    if (!this.context) {
      this.context = new AudioContext();
    }
    const context = this.context;
    if (context.state === 'suspended') await context.resume();
    if (this.node) return;
    await context.audioWorklet.addModule(getPcmPlayerWorkletUrl());
    if (this.context !== context) return; // disposed while the module loaded
    const node = new AudioWorkletNode(context, PCM_PLAYER_PROCESSOR_NAME, {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    });
    node.port.onmessage = (event: MessageEvent<PcmPlayerDrained>) => {
      // A report about an older chunk is stale: a newer one is on its way.
      if (event.data?.type === 'drained' && event.data.seq === this.seq) this.setSpeaking(false);
    };
    node.connect(context.destination);
    this.node = node;
  }

  /** Hand one chunk (at ITS rate) to the worklet; dropped before `warmup()`. */
  enqueue(pcm16: ArrayBuffer, sampleRate: number): void {
    const node = this.node;
    if (!node) return;
    const source = new Int16Array(pcm16);
    if (source.length === 0) return;
    const samples = new Float32Array(source.length);
    for (let i = 0; i < source.length; i++) samples[i] = source[i] / 0x8000;
    this.seq += 1;
    const command: PcmPlayerCommand = { type: 'chunk', seq: this.seq, rate: sampleRate, samples };
    node.port.postMessage(command, [samples.buffer]);
    this.setSpeaking(true);
  }

  /** The provider interrupted: the worklet drops everything it holds, now. */
  flush(): void {
    const command: PcmPlayerCommand = { type: 'flush' };
    this.node?.port.postMessage(command);
    this.setSpeaking(false);
  }

  dispose(): void {
    this.flush();
    if (this.node) {
      this.node.port.onmessage = null;
      this.node.disconnect();
      this.node = null;
    }
    void this.context?.close();
    this.context = null;
    this.listener = null;
  }

  private setSpeaking(value: boolean): void {
    if (this.speaking === value) return;
    this.speaking = value;
    this.listener?.(value);
  }
}
