import { activateRtcAudio } from './rtc-audio-activation';

/** Receive-only capture graph. Tracks are borrowed and never stopped here. */
export class RemotePcmCapture {
  private releaseDecoder: (() => void) | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private mute: GainNode | null = null;
  private epoch = 0;
  private attachment = 0;
  private frameEpoch = 0;
  constructor(
    readonly consume: (pcm: ArrayBuffer, rate: number) => void,
    readonly failed: () => void = () => {}
  ) {}
  async warmup(): Promise<void> {
    this.context ??= new AudioContext();
    await this.context.resume();
  }
  attach(stream: MediaStream): () => void {
    this.detach();
    const epoch = this.epoch;
    const attachment = ++this.attachment;
    this.frameEpoch = 0;
    this.releaseDecoder = activateRtcAudio(stream);
    void this.connect(stream, epoch).catch(() => {
      if (epoch === this.epoch) this.fallback(stream);
    });
    return () => {
      if (attachment === this.attachment) this.detach();
    };
  }
  private async connect(stream: MediaStream, epoch: number): Promise<void> {
    const context = this.context;
    if (!context || context.state !== 'running') throw new Error('remote_audio_not_unlocked');
    await context.audioWorklet.addModule(getRemoteCaptureWorkletUrl());
    if (epoch !== this.epoch || context !== this.context) return;
    const source = context.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(context, REMOTE_CAPTURE_PROCESSOR, {
      numberOfInputs: 1,
      numberOfOutputs: 1,
    });
    const mute = context.createGain();
    mute.gain.value = 0;
    node.port.onmessage = event => {
      const frame: unknown = event.data;
      if (
        epoch !== this.epoch ||
        !frame ||
        typeof frame !== 'object' ||
        !('pcm' in frame) ||
        !('epoch' in frame) ||
        frame.epoch !== this.frameEpoch ||
        !(frame.pcm instanceof ArrayBuffer)
      )
        return;
      try {
        this.consume(frame.pcm, context.sampleRate);
      } catch {
        this.fallback(stream);
      }
    };
    source.connect(node);
    node.connect(mute);
    mute.connect(context.destination);
    this.source = source;
    this.node = node;
    this.mute = mute;
    if (this.frameEpoch) node.port.postMessage({ type: 'flush', epoch: this.frameEpoch });
  }
  flush(): void {
    this.frameEpoch++;
    this.node?.port.postMessage({ type: 'flush', epoch: this.frameEpoch });
  }
  private fallback(stream: MediaStream): void {
    this.detach();
    this.failed();
    const context = this.context;
    if (!context || context.state !== 'running') return;
    // Capture is optional to a native conversation. The original live track
    // can continue locally without replaying or synthesising any prefix.
    const source = context.createMediaStreamSource(stream);
    const gain = context.createGain();
    gain.gain.value = 1;
    source.connect(gain);
    gain.connect(context.destination);
    this.source = source;
    this.mute = gain;
  }
  private detach(): void {
    this.epoch++;
    this.releaseDecoder?.();
    this.releaseDecoder = null;
    if (this.node) this.node.port.onmessage = null;
    this.source?.disconnect();
    this.node?.disconnect();
    this.mute?.disconnect();
    this.source = null;
    this.node = null;
    this.mute = null;
  }
  dispose(): void {
    this.attachment++;
    this.detach();
    const context = this.context;
    this.context = null;
    void context?.close().catch(() => {});
  }
}
export const REMOTE_CAPTURE_PROCESSOR = 'lia-remote-pcm-capture';
export function buildRemoteCaptureWorklet(): string {
  return `class RemotePcmCapture extends AudioWorkletProcessor {
    constructor() {
      super(); this.samples = new Float32Array(1024); this.length = 0; this.epoch = 0;
      this.port.onmessage = event => {
        if (event.data.type === 'flush') { this.length = 0; this.epoch = event.data.epoch; }
      };
    }
    process(inputs) {
      const channels = inputs[0];
      if (!channels || !channels.length) return true;
      for (let i = 0; i < channels[0].length; i++) {
        let mono = 0;
        for (const channel of channels) mono += channel[i] / channels.length;
        this.samples[this.length++] = mono;
        if (this.length === this.samples.length) {
          const pcm = new ArrayBuffer(this.samples.length * 2);
          const view = new DataView(pcm);
          for (let frame = 0; frame < this.samples.length; frame++) {
            const v = Math.max(-1, Math.min(1, this.samples[frame]));
            view.setInt16(frame * 2, Math.round(v * (v < 0 ? 32768 : 32767)), true);
          }
          this.port.postMessage({ pcm, epoch: this.epoch }, [pcm]); this.length = 0;
        }
      }
      return true;
    }
  }
  registerProcessor('${REMOTE_CAPTURE_PROCESSOR}', RemotePcmCapture);`;
}
let workletUrl: string | null = null;
function getRemoteCaptureWorkletUrl(): string {
  workletUrl ??= URL.createObjectURL(
    new Blob([buildRemoteCaptureWorklet()], { type: 'application/javascript' })
  );
  return workletUrl;
}
