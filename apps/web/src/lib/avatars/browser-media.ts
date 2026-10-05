import type { AvatarMedia } from './engine';
/**
 * One native element presents Simli's video; the gesture-resumed AudioContext
 * renders its audio. The element stays MUTED for its whole life: unmuting it
 * needs a `play()` with sound, which a real Chrome refused outside a gesture
 * on 2026-10-04 (a headless Chromium accepted it) — a Live started cold then
 * played every reply locally while the face sat on « connecting ». A context
 * resumed inside the gesture that started the Live stays running without one.
 */
export class BrowserAvatarMedia implements AvatarMedia {
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private gain: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private samples = new Float32Array(256);
  private stream: MediaStream | null = null;
  private element: HTMLVideoElement | null = null;
  private frame = false;
  private videoEpoch = 0;
  private audible: (() => void) | null = null;
  private monitor: ReturnType<typeof setInterval> | null = null;
  private silent = true;
  private removeFrame: (() => void) | null = null;
  constructor(readonly changed: () => void) {}
  get ready(): boolean {
    return this.frame && !!this.source && this.context?.state === 'running';
  }
  get connected(): boolean {
    return this.frame && !!this.source;
  }
  get clock(): number {
    return this.context?.currentTime ?? 0;
  }
  get quiet(): boolean {
    return this.silent;
  }
  /**
   * Called inside a human gesture (the shell's pointer/key listeners, the
   * window's button, a Live start or wake): the context resumes, and a running
   * context needs no further gesture. Where the browser refuses it, the window
   * keeps offering the button.
   */
  async unlock(): Promise<void> {
    try {
      await this.ensureContext().resume();
    } catch {
      /* The explicit unlock button stays available. */
    }
    this.changed();
  }
  private ensureContext(): AudioContext {
    if (this.context) return this.context;
    const context = new AudioContext();
    this.context = context;
    context.onstatechange = () => this.changed();
    this.gain = context.createGain();
    this.gain.gain.value = 0;
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(this.gain);
    this.gain.connect(context.destination);
    return context;
  }
  audio(stream: MediaStream): void {
    this.source?.disconnect();
    const context = this.ensureContext();
    this.source = context.createMediaStreamSource(stream);
    if (this.analyser) this.source.connect(this.analyser);
    this.changed();
  }
  video(stream: MediaStream): void {
    this.stream = stream;
    this.attach(this.element);
  }
  attach(element: HTMLVideoElement | null): void {
    this.removeFrame?.();
    this.removeFrame = null;
    this.videoEpoch++;
    if (this.element && this.element !== element) this.element.srcObject = null;
    this.element = element;
    this.frame = false;
    if (!element || !this.stream) {
      this.changed();
      return;
    }
    const epoch = this.videoEpoch;
    // Muted for life: the element only shows the face. Chromium still needs
    // the stream on a media element for Web Audio to receive the remote track.
    element.muted = true;
    element.playsInline = true;
    element.srcObject = this.stream;
    const rendered = () => {
      if (epoch !== this.videoEpoch) return;
      this.frame = true;
      this.changed();
    };
    if (typeof element.requestVideoFrameCallback === 'function') {
      const id = element.requestVideoFrameCallback(rendered);
      this.removeFrame = () => element.cancelVideoFrameCallback(id);
    } else {
      element.addEventListener('loadeddata', rendered, { once: true });
      this.removeFrame = () => element.removeEventListener('loadeddata', rendered);
    }
    void element.play().catch(() => {
      if (epoch === this.videoEpoch) this.changed();
    });
  }
  begin(onAudible: () => void): void {
    this.mute();
    this.audible = onAudible;
    if (this.gain) this.gain.gain.value = 1;
    this.monitor = setInterval(() => {
      this.analyser?.getFloatTimeDomainData(this.samples);
      // This is an output observation, never a filter on PCM sent to Simli.
      this.silent = !this.samples.some(value => Math.abs(value) > 1e-7);
      if (!this.silent && this.context?.state === 'running') {
        const callback = this.audible;
        this.audible = null;
        callback?.();
      }
    }, 20);
  }
  mute(): void {
    if (this.gain) this.gain.gain.value = 0;
    if (this.monitor) clearInterval(this.monitor);
    this.monitor = null;
    this.audible = null;
    this.silent = true;
  }
  reset(destroy = false): void {
    this.mute();
    this.videoEpoch++;
    this.removeFrame?.();
    this.removeFrame = null;
    this.frame = false;
    this.stream = null;
    if (this.element) this.element.srcObject = null;
    this.source?.disconnect();
    this.source = null;
    // Keep the gesture-resumed context across a controlled renewal. Its
    // owner disposes it at shell teardown; no stream remains attached here.
    if (!destroy) return;
    this.analyser?.disconnect();
    this.analyser = null;
    this.gain?.disconnect();
    this.gain = null;
    const context = this.context;
    this.context = null;
    if (context) {
      context.onstatechange = null;
      void context.close().catch(() => {});
    }
  }
}
