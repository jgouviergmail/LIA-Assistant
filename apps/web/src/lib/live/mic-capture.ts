/**
 * The microphone, opened ONCE by the controller (ADR-258's one-owner rule) at
 * the rate the transport declares (ADR-299, spec §1.5; wave 2 spec A11).
 *
 * `pcm` (Gemini): int16 chunks through the SAME worklet the push-to-talk and
 * the meeting recorder use, at the chunk size the provider wants (tens of
 * milliseconds, not a quarter second). `pcm: false` (a native transport such
 * as WebRTC): the stream alone — the transport carries the track, a mute
 * disables it. One capture owns its stream, context and node, and releases
 * all three — including on a failure halfway through the setup, so a refused
 * worklet never leaves a microphone light on.
 */
import { PCM_WORKLET_PROCESSOR_NAME, getPcmWorkletUrl } from '@/lib/audio/pcm-worklet';

export interface MicCaptureOptions {
  /** The input rate the transport declares. */
  sampleRate: number;
  /** Samples per chunk, derived from the transport's chunk length. */
  chunkSamples: number;
  onChunk: (pcm16: ArrayBuffer) => void;
  /** False for a transport that takes the stream and carries the audio itself. */
  pcm?: boolean;
}

export interface MicCapture {
  /** The captured stream, for a transport that carries the track itself. */
  readonly stream: MediaStream;
  /** Drop chunks (or disable the track) instead of delivering them. */
  mute(on: boolean): void;
  stop(): Promise<void>;
}

async function releaseStream(stream: MediaStream): Promise<void> {
  for (const track of stream.getTracks()) track.stop();
}

async function openStream(sampleRate: number): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
}

/** The stream alone: a native transport carries it, a mute disables the track. */
function nativeCapture(stream: MediaStream): MicCapture {
  let stopped = false;
  return {
    stream,
    mute(on: boolean) {
      for (const track of stream.getAudioTracks()) track.enabled = !on;
    },
    async stop() {
      if (stopped) return;
      stopped = true;
      await releaseStream(stream);
    },
  };
}

export async function startMicCapture(options: MicCaptureOptions): Promise<MicCapture> {
  if (options.pcm === false) return nativeCapture(await openStream(options.sampleRate));
  // Open the context BEFORE getUserMedia. Creating a second AudioContext after
  // capture begins matches a documented iOS WebKit distortion sequence; both
  // Gemini and ElevenLabs use this PCM path, while WebRTC owns its own media.
  const context = new AudioContext({ sampleRate: options.sampleRate });
  let stream: MediaStream;
  try {
    stream = await openStream(options.sampleRate);
  } catch (error) {
    await context.close();
    throw error;
  }
  let node: AudioWorkletNode;
  try {
    await context.audioWorklet.addModule(getPcmWorkletUrl(options.chunkSamples));
    node = new AudioWorkletNode(context, PCM_WORKLET_PROCESSOR_NAME);
  } catch (error) {
    await releaseStream(stream);
    await context.close();
    throw error;
  }
  let source: MediaStreamAudioSourceNode;
  let muted = false;
  let stopped = false;
  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    if (!muted && !stopped) options.onChunk(event.data);
  };
  try {
    source = context.createMediaStreamSource(stream);
    source.connect(node);
    if (context.state === 'suspended') await context.resume();
  } catch (error) {
    node.port.onmessage = null;
    node.disconnect();
    await releaseStream(stream);
    await context.close();
    throw error;
  }
  return {
    stream,
    mute(on: boolean) {
      muted = on;
    },
    async stop() {
      if (stopped) return;
      stopped = true;
      node.port.onmessage = null;
      source.disconnect();
      node.disconnect();
      await releaseStream(stream);
      await context.close();
    },
  };
}
