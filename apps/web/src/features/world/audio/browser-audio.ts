import { readPublicAssetResponse } from '@/lib/api-client';
import { WORLD_AUDIO_CACHE_BYTES } from './soundscape';
import { soundUrl, type SoundId } from './catalogue';
import type { DecodedSound, SoundBackend, SoundVoice } from './soundscape';
const MAX_ENCODED = 512 * 1024;
async function boundedAudio(response: Response): Promise<ArrayBuffer> {
  if (!response.ok || !response.body) throw new Error('World sound unavailable');
  const size = Number(response.headers.get('content-length'));
  if (size > MAX_ENCODED) throw new Error('World sound too large');
  const reader = response.body.getReader(),
    chunks: Uint8Array[] = [];
  let length = 0;
  try {
    for (;;) {
      const part = await reader.read();
      if (part.done) break;
      length += part.value.length;
      if (length > MAX_ENCODED) throw new Error('World sound too large');
      chunks.push(part.value);
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  return bytes.buffer;
}
function ramp(context: AudioContext, param: AudioParam, level: number, seconds: number): void {
  const now = context.currentTime;
  if (typeof param.cancelAndHoldAtTime === 'function') param.cancelAndHoldAtTime(now);
  else {
    param.cancelScheduledValues(now);
    param.setValueAtTime(param.value, now);
  }
  param.linearRampToValueAtTime(Math.max(0, Math.min(1, level)), now + Math.max(0.005, seconds));
}
function voice(
  context: AudioContext,
  buffer: AudioBuffer,
  output: AudioNode,
  loop: boolean,
  offset: number
): SoundVoice {
  const source = context.createBufferSource(),
    gain = context.createGain();
  source.buffer = buffer;
  source.loop = loop;
  gain.gain.value = 0;
  source.connect(gain);
  gain.connect(output);
  let ended = false;
  source.onended = () => {
    ended = true;
    source.disconnect();
    gain.disconnect();
    source.buffer = null;
  };
  try {
    source.start(0, offset);
  } catch (error) {
    source.disconnect();
    gain.disconnect();
    throw error;
  }
  return {
    fade: (level, seconds) => {
      if (!ended && context.state !== 'closed') ramp(context, gain.gain, level, seconds);
    },
    stop: (seconds = 0) => {
      if (ended) return;
      try {
        source.stop(context.currentTime + Math.max(0, seconds));
      } catch {
        /* Already stopped by the browser. */
      }
    },
  };
}
/** AudioContext is created only from the caller's deliberate activation. No audio DOM or microphone. */
export class BrowserWorldAudio implements SoundBackend {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private volume = 1;
  private closed = false;
  private wantsAudio = false;
  private activation = 0;
  setVolume(level: number): void {
    if (this.closed || !Number.isFinite(level)) return;
    this.volume = Math.max(0, Math.min(1, level));
    if (this.context && this.master && this.context.state !== 'closed')
      ramp(this.context, this.master.gain, this.volume, 0.05);
  }
  async activate(): Promise<boolean> {
    if (this.closed || typeof AudioContext === 'undefined') return false;
    this.wantsAudio = true;
    const attempt = ++this.activation;
    this.context ??= new AudioContext({ latencyHint: 'playback', sampleRate: 32000 });
    const context = this.context;
    if (context.state === 'closed') return false;
    if (!this.master) {
      this.master = context.createGain();
      this.master.gain.value = this.volume;
      this.master.connect(context.destination);
    }
    if (context.state === 'running') return true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const resumed = context
      .resume()
      .then(() => {
        if (!this.wantsAudio && context.state === 'running') void context.suspend().catch(() => {});
        return !this.closed && this.wantsAudio && context.state === 'running';
      })
      .catch(() => false);
    try {
      const ready = await Promise.race([
        resumed,
        new Promise<boolean>(resolve => {
          timer = setTimeout(() => resolve(false), 2500);
        }),
      ]);
      if (!ready && this.activation === attempt) this.wantsAudio = false;
      return ready;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }
  async load(id: SoundId, signal: AbortSignal): Promise<DecodedSound> {
    const context = this.context,
      output = this.master;
    if (!context || !output || this.closed) throw new Error('World audio inactive');
    const timeout = new AbortController(),
      cancel = () => timeout.abort();
    signal.addEventListener('abort', cancel, { once: true });
    if (signal.aborted) cancel();
    const timer = setTimeout(cancel, 12000);
    try {
      const response = await readPublicAssetResponse(soundUrl(id), timeout.signal);
      const bytes = await boundedAudio(response);
      const buffer = await context.decodeAudioData(bytes);
      if (timeout.signal.aborted || this.closed) throw new Error('World audio cancelled');
      if (
        buffer.duration > 33 ||
        buffer.numberOfChannels > 2 ||
        buffer.length * buffer.numberOfChannels * 4 > WORLD_AUDIO_CACHE_BYTES
      )
        throw new Error('World audio decode outside bounds');
      return {
        duration: buffer.duration,
        bytes: buffer.length * buffer.numberOfChannels * 4,
        start: (loop, offset) => voice(context, buffer, output, loop, offset),
      };
    } finally {
      clearTimeout(timer);
      signal.removeEventListener('abort', cancel);
    }
  }
  suspend(): void {
    this.wantsAudio = false;
    if (this.context?.state === 'running') void this.context.suspend().catch(() => {});
  }
  destroy(): void {
    this.closed = true;
    this.wantsAudio = false;
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {});
    this.master?.disconnect();
    this.master = null;
    this.context = null;
  }
}
