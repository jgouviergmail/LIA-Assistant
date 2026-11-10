/** A phrase's strongest existing stress cues one hand stroke, followed by its wrist. */
import { limbArticulation, type RigCharacterId } from './acting-profile';
import type { LimbChannel } from './channels';
import { hasLimb } from './limbs';
import { SPEECH_PHRASE_GAP_MIN_MS } from './speech';
import { tapeDurationMs, type Tape, type TapeKey } from './tape';

const HANDS = ['armL', 'armR', 'wristL', 'wristR'] as const satisfies readonly LimbChannel[];
interface Phrase {
  start: number;
  end: number;
  leftLeads: boolean;
}

function phrases(mouth: Tape): Phrase[] {
  const result: Phrase[] = [];
  let first = mouth.keys[0];
  for (let index = 0; index < mouth.keys.length; index += 1) {
    const key = mouth.keys[index];
    const next = mouth.keys[index + 1];
    if (key.value !== 0 || (next && next.atMs - key.atMs < SPEECH_PHRASE_GAP_MIN_MS)) continue;
    result.push({ start: first.atMs, end: key.atMs, leftLeads: first.value > 0.44 });
    first = next;
  }
  return result;
}

function strokeKeys(
  phrase: Phrase,
  stress: TapeKey,
  channel: (typeof HANDS)[number],
  articulation: ReturnType<typeof limbArticulation>
): TapeKey[] {
  const wrist = channel.startsWith('wrist');
  const left = channel.endsWith('L');
  const gain = (left === phrase.leftLeads ? 1 : 0.28) * articulation.accent;
  const strength = Math.min(1, Math.abs(stress.value) / 0.055);
  const size = (wrist ? 5.5 : 10) * strength * gain * (left ? 1 : -1);
  const trail = wrist ? articulation.wristLag : 0;
  const accent = stress.atMs + 70 + trail;
  const release = Math.min(
    phrase.end,
    stress.atMs + Math.round(810 * articulation.recovery) + trail
  );
  return [
    { atMs: Math.max(phrase.start, stress.atMs - 240), value: 0 },
    { atMs: Math.max(phrase.start, stress.atMs - 100 + trail), value: -size * 0.07 },
    { atMs: accent, value: size },
    { atMs: Math.min(release - 120, accent + 190), value: size * 0.88 },
    { atMs: release, value: 0 },
  ];
}

/** Read the existing speech score: no new draws, syllable flapping or repeating chunk. */
export function limbSpeechTapes(tapes: readonly Tape[], identity: RigCharacterId): Tape[] {
  const mouth = tapes.find(tape => tape.channel === 'mouthOpen');
  const brows = tapes.find(tape => tape.channel === 'browYL');
  if (!mouth || !hasLimb(identity, 'armL')) return [];
  const articulation = limbArticulation(identity);
  // Leave the distal stroke time to complete before the lips close.
  const tail = 300 + articulation.wristLag;
  const accents = phrases(mouth).flatMap(phrase => {
    const stress = brows?.keys
      .filter(
        key => key.atMs >= phrase.start && key.atMs <= phrase.end - tail && key.value < -0.038
      )
      .reduce<
        TapeKey | undefined
      >((best, key) => (!best || key.value < best.value ? key : best), undefined);
    return stress ? [{ phrase, stress }] : [];
  });
  if (accents.length === 0) return [];
  return HANDS.filter(channel => hasLimb(identity, channel)).map(channel => ({
    channel,
    relative: true,
    interpolation: 'smooth',
    durationMs: tapeDurationMs(mouth),
    spring: { frequency: channel.startsWith('wrist') ? 3.1 : 3.8, damping: 1 },
    keys: [
      { atMs: 0, value: 0 },
      ...accents.flatMap(({ phrase, stress }) => strokeKeys(phrase, stress, channel, articulation)),
    ],
  }));
}
