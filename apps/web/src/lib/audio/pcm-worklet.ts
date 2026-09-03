/**
 * The 16 kHz int16 PCM AudioWorklet — ONE source, two consumers.
 *
 * `useVoiceInput` (push-to-talk) and the meeting recorder both need the same
 * thing from the microphone: Float32 frames folded into little-endian int16
 * chunks of a fixed size. The processor used to live inline in the voice hook;
 * a second copy for meetings would have been the drift class this repo keeps
 * paying for, so the source is built here and cached per chunk size.
 *
 * The module runs inside the AudioWorklet global scope, so it is shipped as a
 * string turned into a Blob URL — a bundler cannot import it as a module.
 */

/** Name registered with `registerProcessor`; the node is created with it. */
export const PCM_WORKLET_PROCESSOR_NAME = 'lia-pcm-int16-processor';

/**
 * Source of the worklet module for one chunk size.
 *
 * @param chunkSize - Samples per posted chunk (the port receives one
 *   `ArrayBuffer` of `chunkSize * 2` bytes per message).
 * @returns JavaScript source of the worklet module.
 */
export function buildPcmWorkletSource(chunkSize: number): string {
  const size = Math.max(1, Math.floor(chunkSize));
  return `
    class LiaPcmInt16Processor extends AudioWorkletProcessor {
      constructor() {
        super();
        this.buffer = [];
        this.chunkSize = ${size};
      }

      process(inputs) {
        const input = inputs[0];
        if (input.length > 0) {
          const samples = input[0];
          for (let i = 0; i < samples.length; i++) {
            this.buffer.push(samples[i]);
          }
          while (this.buffer.length >= this.chunkSize) {
            const chunk = this.buffer.splice(0, this.chunkSize);
            const int16Array = new Int16Array(chunk.length);
            for (let i = 0; i < chunk.length; i++) {
              const s = Math.max(-1, Math.min(1, chunk[i]));
              int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            this.port.postMessage(int16Array.buffer, [int16Array.buffer]);
          }
        }
        return true;
      }
    }

    registerProcessor('${PCM_WORKLET_PROCESSOR_NAME}', LiaPcmInt16Processor);
  `;
}

const urlCache = new Map<number, string>();

/**
 * Blob URL of the worklet module for `chunkSize`, created once per page.
 *
 * @param chunkSize - Samples per posted chunk.
 * @returns A `blob:` URL suitable for `audioWorklet.addModule`.
 */
export function getPcmWorkletUrl(chunkSize: number): string {
  const cached = urlCache.get(chunkSize);
  if (cached) return cached;
  const blob = new Blob([buildPcmWorkletSource(chunkSize)], { type: 'application/javascript' });
  const url = URL.createObjectURL(blob);
  urlCache.set(chunkSize, url);
  return url;
}

/**
 * RMS level of one int16 chunk, in [0, 1] — the recorder's level meter.
 *
 * @param buffer - Little-endian int16 samples.
 * @returns Root mean square normalised to full scale.
 */
export function int16Rms(buffer: ArrayBuffer): number {
  const samples = new Int16Array(buffer);
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i] / 0x8000;
    sum += s * s;
  }
  return Math.sqrt(sum / samples.length);
}
