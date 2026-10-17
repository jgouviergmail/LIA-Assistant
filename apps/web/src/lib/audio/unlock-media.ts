/** A short silent clip primes the same media element within a user gesture. */

/** Silent stereo priming (0.1 s, 8 kHz, PCM8). */
function silentWav(): string {
  const channels = 2;
  const samples = 800 * channels;
  const bytes = new Uint8Array(44 + samples);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string): void => {
    for (let index = 0; index < text.length; index += 1) {
      bytes[offset + index] = text.charCodeAt(index);
    }
  };
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + samples, true);
  ascii(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 8000 * channels, true);
  view.setUint16(32, channels, true);
  view.setUint16(34, 8, true);
  ascii(36, 'data');
  view.setUint32(40, samples, true);
  bytes.fill(128, 44);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `data:audio/wav;base64,${btoa(binary)}`;
}

let silence: string | null = null;

export interface UnlockableMedia {
  src: string;
  play(): Promise<void>;
  pause(): void;
}

/** Play once inside the gesture so the browser lets this element play later. */
export function unlockMedia(element: UnlockableMedia): void {
  const quiet = (silence ??= silentWav());
  element.src = quiet;
  void element
    .play()
    .then(() => {
      // A real clip may already have replaced the silence: never pause it.
      if (element.src === quiet) element.pause();
    })
    .catch(() => undefined);
}
