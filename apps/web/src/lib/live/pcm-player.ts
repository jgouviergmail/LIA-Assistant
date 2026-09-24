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
  | { type: 'buffer'; frames: number }
  | { type: 'flush' };

/** What the worklet posts back: the queue ran dry after chunk `seq`. */
export interface PcmPlayerDrained {
  type: 'drained';
  seq: number;
}

/** Actual silent frames rendered between two runs of provider audio. */
export interface PcmPlayerGap {
  type: 'gap';
  frames: number;
  at_frames: number;
}

/** Counts only: enough to distinguish network starvation from rendering distortion. */
export interface PcmPlayerDiagnostics {
  chunks: number;
  drains: number;
  audio_ms: number;
  source_rate: number;
  context_rate: number;
  short_gap_count: number;
  short_gap_ms: number;
  short_gap_bins: number[];
  long_gap_count: number;
  max_gap_ms: number;
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
        this.attack = 0;
        this.attackFrom = 0;
        this.lastOutput = 0;
        this.wasEmpty = true;
        this.tailFrames = 16;
        this.tailStart = 0;
        this.bufferFrames = 0;
        this.waitFrames = 0;
        this.renderedFrames = 0;
        this.firstChunkFrame = null;
        this.playingEver = false;
        this.gapFrames = 0;
        this.port.onmessage = (event) => {
          const message = event.data;
          if (message.type === 'chunk') {
            if (this.firstChunkFrame === null) this.firstChunkFrame = this.renderedFrames;
            // The queue can drain exactly at a render-block boundary without
            // playing any silence. Rebuffer only after silence was rendered.
            if (this.queue.length === 0 && this.wasEmpty) {
              if (this.gapFrames > 0) {
                this.port.postMessage({
                  type: 'gap',
                  frames: this.gapFrames,
                  at_frames: this.renderedFrames - this.firstChunkFrame,
                });
                this.gapFrames = 0;
              }
              this.waitFrames = this.bufferFrames;
            }
            this.queue.push({ samples: message.samples, rate: message.rate, seq: message.seq });
          } else if (message.type === 'buffer') {
            this.bufferFrames = message.frames;
          } else if (message.type === 'flush') {
            this.queue.length = 0;
            this.position = 0;
            this.playing = false;
            this.attack = 0;
            this.attackFrom = 0;
            this.lastOutput = 0;
            this.wasEmpty = true;
            this.tailFrames = 16;
            this.tailStart = 0;
            this.waitFrames = 0;
            this.playingEver = false;
            this.gapFrames = 0;
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
          if (this.waitFrames > 0 && this.queue.length > 0) {
            this.waitFrames -= 1;
            output[i] = 0;
            continue;
          }
          if (this.queue.length === 0) {
            if (!this.wasEmpty) {
              this.wasEmpty = true;
              this.tailStart = this.lastOutput;
              this.tailFrames = 0;
            }
            this.tailFrames = Math.min(16, this.tailFrames + 1);
            output[i] = this.tailStart * (1 - this.tailFrames / 16);
            this.lastOutput = output[i];
            if (this.playingEver) this.gapFrames += 1;
            continue;
          }
          if (this.wasEmpty) {
            this.wasEmpty = false;
            this.attack = 0;
            this.attackFrom = this.lastOutput;
          }
          const head = this.queue[0];
          const index = Math.floor(this.position);
          const fraction = this.position - index;
          const a = head.samples[index];
          let b;
          if (index + 1 < head.samples.length) b = head.samples[index + 1];
          else if (this.queue.length > 1) b = this.queue[1].samples[0];
          else b = a;
          // Keep adjacent chunks untouched. Only an ACTUAL empty queue gets
          // a short tail; a later chunk fades from the last rendered sample.
          const raw = a + (b - a) * fraction;
          if (this.attack < 16) {
            this.attack += 1;
            const gain = this.attack / 16;
            output[i] = this.attackFrom * (1 - gain) + raw * gain;
          } else {
            output[i] = raw;
          }
          this.lastOutput = output[i];
          this.position += head.rate / sampleRate;
          this.playing = true;
          this.playingEver = true;
        }
        this.renderedFrames += output.length;
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
  private drains = 0;
  private audioMs = 0;
  private sourceRate = 0;
  private shortGapCount = 0;
  private shortGapMs = 0;
  private shortGapBins = new Array<number>(12).fill(0);
  private longGapCount = 0;
  private maxGapMs = 0;

  constructor(private readonly bufferMs = 0) {}

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
    node.port.onmessage = (event: MessageEvent<PcmPlayerDrained | PcmPlayerGap>) => {
      if (event.data?.type === 'gap') {
        const gapMs = Math.round((event.data.frames / context.sampleRate) * 1000);
        this.maxGapMs = Math.max(this.maxGapMs, gapMs);
        if (gapMs > 250) {
          this.longGapCount += 1;
        } else if (gapMs > 0) {
          this.shortGapCount += 1;
          this.shortGapMs += gapMs;
          const bin = Math.min(
            this.shortGapBins.length - 1,
            Math.floor(event.data.at_frames / context.sampleRate / 10)
          );
          this.shortGapBins[bin] += 1;
        }
      }
      if (event.data?.type === 'drained') this.drains += 1;
      // A report about an older chunk is stale: a newer one is on its way.
      if (event.data?.type === 'drained' && event.data.seq === this.seq) this.setSpeaking(false);
    };
    node.connect(context.destination);
    if (this.bufferMs > 0) {
      const command: PcmPlayerCommand = {
        type: 'buffer',
        frames: Math.round((context.sampleRate * this.bufferMs) / 1000),
      };
      node.port.postMessage(command);
    }
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
    if (Number.isFinite(sampleRate) && sampleRate > 0) {
      this.audioMs += (source.length / sampleRate) * 1000;
      this.sourceRate = sampleRate;
    }
    const command: PcmPlayerCommand = { type: 'chunk', seq: this.seq, rate: sampleRate, samples };
    node.port.postMessage(command, [samples.buffer]);
    this.setSpeaking(true);
  }

  diagnostics(): PcmPlayerDiagnostics | null {
    if (this.seq === 0) return null;
    return {
      chunks: this.seq,
      drains: this.drains,
      audio_ms: Math.round(this.audioMs),
      source_rate: this.sourceRate,
      context_rate: this.context?.sampleRate ?? 0,
      short_gap_count: this.shortGapCount,
      short_gap_ms: this.shortGapMs,
      short_gap_bins: this.shortGapBins,
      long_gap_count: this.longGapCount,
      max_gap_ms: this.maxGapMs,
    };
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
