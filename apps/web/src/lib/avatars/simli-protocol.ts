export type SimliControl =
  | 'START'
  | 'ACK'
  | 'SPEAK'
  | 'SILENT'
  | 'STOP'
  | 'RATE'
  | 'ERROR'
  | 'CLOSING';
export type SimliSignal =
  | { kind: 'control'; control: SimliControl }
  | { kind: 'answer'; sdp: string }
  | { kind: 'unknown' };
const CONTROLS: readonly SimliControl[] = [
  'START',
  'ACK',
  'SPEAK',
  'SILENT',
  'STOP',
  'RATE',
  'ERROR',
  'CLOSING',
];

function isControl(value: string): value is SimliControl {
  return CONTROLS.some(control => control === value);
}

/** Reviewed Compose P2P wire. No raw provider text escapes the parser. */
export function parseSimliSignal(input: unknown): SimliSignal {
  if (typeof input !== 'string' || input.length > 65536) return { kind: 'unknown' };
  const control = input.trim().split(/\s+/, 1)[0].toUpperCase();
  if (isControl(control)) return { kind: 'control', control };
  try {
    const value: unknown = JSON.parse(input);
    if (typeof value !== 'object' || value === null) return { kind: 'unknown' };
    if (
      'type' in value &&
      value.type === 'answer' &&
      'sdp' in value &&
      typeof value.sdp === 'string' &&
      value.sdp.startsWith('v=0') &&
      value.sdp.length <= 32768
    ) {
      return { kind: 'answer', sdp: value.sdp };
    }
  } catch {
    /* Non-JSON controls not declared by this wire are ignored. */
  }
  return { kind: 'unknown' };
}
