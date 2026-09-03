/**
 * The two microphone sources of the meeting recorder (ADR-258).
 *
 * Both hand the recorder the same two things — a segment Blob every
 * `segmentSeconds`, and a level reading for the meter and the silence
 * watchdog — so the recorder never knows which one it holds:
 *
 *  - {@link PcmWorkletSource}: the shared int16 worklet (`lib/audio/pcm-worklet`);
 *    chunks are folded into raw PCM segments, the level is computed from the
 *    samples themselves.
 *  - {@link OpusRecorderSource}: `MediaRecorder` with a timeslice; the level
 *    comes from an `AnalyserNode` since the encoded bytes cannot be read.
 *
 * A source owns nothing it did not create: the stream is the recorder's, the
 * source only opens contexts and nodes on it and closes them in `stop()`.
 */

import { VOICE_INPUT_CHUNK_SIZE, VOICE_INPUT_SAMPLE_RATE } from '@/lib/constants';
import { PCM_WORKLET_PROCESSOR_NAME, getPcmWorkletUrl, int16Rms } from '@/lib/audio/pcm-worklet';

export interface AudioSourceCallbacks {
  /** One segment, ready to upload in sequence order. */
  onSegment: (blob: Blob) => void;
  /** RMS level in [0, 1], a few times per second. */
  onLevel: (rms: number) => void;
  /** A failure the source cannot recover from (the recorder stops). */
  onError: (error: Error) => void;
}

export interface MeetingAudioSource {
  /** Open the pipeline on `stream` and start emitting segments. */
  start(stream: MediaStream): Promise<void>;
  /** Flush the final segment and release every node/context this source opened. */
  stop(): Promise<void>;
}

/** Bytes of one second of 16 kHz int16 mono PCM. */
const PCM_BYTES_PER_SECOND = VOICE_INPUT_SAMPLE_RATE * 2;
/** Level readings per second, for both sources. */
const LEVEL_INTERVAL_MS = 250;
/** Opus target bitrate — transparent for speech, 240 kB per minute. */
const OPUS_BITS_PER_SECOND = 32_000;

// ----------------------------------------------------------------------------
// PCM
// ----------------------------------------------------------------------------

export class PcmWorkletSource implements MeetingAudioSource {
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private parts: ArrayBuffer[] = [];
  private bufferedBytes = 0;
  private levelTimer: ReturnType<typeof setInterval> | null = null;
  private levelAccumulator: number[] = [];
  private readonly segmentBytes: number;

  constructor(
    private readonly callbacks: AudioSourceCallbacks,
    segmentSeconds: number
  ) {
    this.segmentBytes = Math.max(1, Math.floor(segmentSeconds * PCM_BYTES_PER_SECOND));
  }

  async start(stream: MediaStream): Promise<void> {
    const context = new AudioContext({ sampleRate: VOICE_INPUT_SAMPLE_RATE });
    this.context = context;
    await context.audioWorklet.addModule(getPcmWorkletUrl(VOICE_INPUT_CHUNK_SIZE));
    const node = new AudioWorkletNode(context, PCM_WORKLET_PROCESSOR_NAME);
    node.port.onmessage = event => this.onChunk(event.data as ArrayBuffer);
    this.node = node;
    this.sourceNode = context.createMediaStreamSource(stream);
    this.sourceNode.connect(node);
    // A worklet with no downstream is culled by some engines: keep it alive
    // through a muted gain so the graph is "connected" without audible output.
    const sink = context.createGain();
    sink.gain.value = 0;
    node.connect(sink);
    sink.connect(context.destination);
    this.levelTimer = setInterval(() => this.publishLevel(), LEVEL_INTERVAL_MS);
  }

  private onChunk(buffer: ArrayBuffer): void {
    this.parts.push(buffer);
    this.bufferedBytes += buffer.byteLength;
    this.levelAccumulator.push(int16Rms(buffer));
    if (this.bufferedBytes >= this.segmentBytes) this.flush();
  }

  private publishLevel(): void {
    if (this.levelAccumulator.length === 0) {
      this.callbacks.onLevel(0);
      return;
    }
    const mean = this.levelAccumulator.reduce((a, b) => a + b, 0) / this.levelAccumulator.length;
    this.levelAccumulator = [];
    this.callbacks.onLevel(mean);
  }

  private flush(): void {
    if (this.parts.length === 0) return;
    const blob = new Blob(this.parts, { type: 'application/octet-stream' });
    this.parts = [];
    this.bufferedBytes = 0;
    this.callbacks.onSegment(blob);
  }

  async stop(): Promise<void> {
    if (this.levelTimer !== null) {
      clearInterval(this.levelTimer);
      this.levelTimer = null;
    }
    if (this.node) {
      this.node.port.onmessage = null;
      this.node.disconnect();
      this.node = null;
    }
    this.sourceNode?.disconnect();
    this.sourceNode = null;
    this.flush();
    if (this.context) {
      await this.context.close().catch(() => undefined);
      this.context = null;
    }
  }
}

// ----------------------------------------------------------------------------
// Opus (MediaRecorder)
// ----------------------------------------------------------------------------

export class OpusRecorderSource implements MeetingAudioSource {
  private recorder: MediaRecorder | null = null;
  private meterContext: AudioContext | null = null;
  private meterTimer: ReturnType<typeof setInterval> | null = null;
  private stopped: Promise<void> | null = null;

  constructor(
    private readonly callbacks: AudioSourceCallbacks,
    private readonly segmentSeconds: number,
    private readonly mimeType: string
  ) {}

  async start(stream: MediaStream): Promise<void> {
    const recorder = new MediaRecorder(stream, {
      mimeType: this.mimeType,
      audioBitsPerSecond: OPUS_BITS_PER_SECOND,
    });
    recorder.ondataavailable = event => {
      if (event.data && event.data.size > 0) this.callbacks.onSegment(event.data);
    };
    recorder.onerror = () => {
      this.callbacks.onError(new Error('MediaRecorder failed'));
    };
    this.stopped = new Promise<void>(resolve => {
      recorder.onstop = () => resolve();
    });
    this.recorder = recorder;
    this.startMeter(stream);
    recorder.start(Math.max(1000, Math.floor(this.segmentSeconds * 1000)));
  }

  private startMeter(stream: MediaStream): void {
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    this.meterContext = context;
    this.meterTimer = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
      this.callbacks.onLevel(Math.sqrt(sum / samples.length));
    }, LEVEL_INTERVAL_MS);
  }

  async stop(): Promise<void> {
    if (this.meterTimer !== null) {
      clearInterval(this.meterTimer);
      this.meterTimer = null;
    }
    if (this.meterContext) {
      await this.meterContext.close().catch(() => undefined);
      this.meterContext = null;
    }
    const recorder = this.recorder;
    this.recorder = null;
    if (recorder && recorder.state !== 'inactive') {
      // `stop()` fires a last `dataavailable` (the tail) before `stop`.
      recorder.stop();
      await this.stopped;
    }
  }
}

/**
 * Build the source matching a chosen format.
 *
 * @param format - The format decided at start.
 * @param mimeType - `MediaRecorder` MIME type for the Opus formats.
 * @param segmentSeconds - Segment cadence published by the server.
 * @param callbacks - Where segments, levels and errors go.
 * @returns The source; the recorder starts it once it holds the stream.
 */
export function createAudioSource(
  format: 'pcm_s16le_16' | 'webm_opus' | 'ogg_opus',
  mimeType: string | undefined,
  segmentSeconds: number,
  callbacks: AudioSourceCallbacks
): MeetingAudioSource {
  if (format === 'pcm_s16le_16' || !mimeType) {
    return new PcmWorkletSource(callbacks, segmentSeconds);
  }
  return new OpusRecorderSource(callbacks, segmentSeconds, mimeType);
}
