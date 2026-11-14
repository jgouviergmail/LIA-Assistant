/**
 * Sound effects placed on the film's frames. Sources are original effects
 * generated for this film (ElevenLabs Sound Effects v2 through the Stewdio
 * connector, `exports/lia-motion/promo/sfx-takes/`), the cleaner of two takes
 * chosen by measurement (single transient, no tail noise). Levels sit under
 * the music; offsets put each sound's measured peak on its visual event.
 */
import { ENUMERATIONS, beat, sectionFrom, type EnumerationId } from './timing.ts';

export type SfxName =
  | 'whoosh-fast'
  | 'whoosh-long'
  | 'click'
  | 'pop'
  | 'notification'
  | 'success'
  | 'typing'
  | 'shimmer'
  | 'impact'
  | 'tap'
  | 'swish';

/** Measured time from a file's start to its peak, in frames at 60 fps. */
const PEAK: Record<SfxName, number> = {
  'whoosh-fast': 9,
  'whoosh-long': 21,
  click: 2,
  pop: 1,
  notification: 0,
  success: 1,
  typing: 0,
  shimmer: 0,
  impact: 0,
  tap: 7,
  swish: 18,
};

/** Clip length to mount, in seconds (each file's own duration). */
const LENGTH: Record<SfxName, number> = {
  'whoosh-fast': 0.8,
  'whoosh-long': 1.6,
  click: 0.5,
  pop: 0.5,
  notification: 1.2,
  success: 1.2,
  typing: 2.5,
  shimmer: 2.0,
  impact: 2.5,
  tap: 0.5,
  swish: 0.6,
};

export type SfxCue = { frame: number; sound: SfxName; volume: number; length: number };

/** A cue whose PEAK lands on `frame`. */
const at = (frame: number, sound: SfxName, volume: number): SfxCue => ({
  frame: Math.max(0, Math.round(frame - PEAK[sound])),
  sound,
  volume,
  length: Math.round(LENGTH[sound] * 60),
});

const CONTEXT = sectionFrom('context');
const ACTION = sectionFrom('action');
const ANTICIPATE = sectionFrom('anticipate');
const DEVICES = sectionFrom('devices');
const LINKED = sectionFrom('linked');
const OUTRO = sectionFrom('outro');

/** An enumeration: a whoosh as its headline lands, one pop per tile, a whoosh as it leaves. */
function enumeration(id: EnumerationId): SfxCue[] {
  const at0 = sectionFrom(id);
  const { first, step, tiles, exit } = ENUMERATIONS[id];
  return [
    at(at0 + 2, 'whoosh-fast', 0.42),
    ...Array.from({ length: tiles }, (_, i) => at(at0 + first + i * step, 'pop', 0.78)),
    at(at0 + exit + 8, 'whoosh-fast', 0.36),
  ];
}

export const SFX_CUES: SfxCue[] = [
  // Opening: one tile per beat, the scattered letters, the thread, the drop.
  ...Array.from({ length: 10 }, (_, i) => at(beat(1 + i), 'pop', 0.8)),
  at(356, 'swish', 0.55),
  at(424, 'shimmer', 0.55),
  at(beat(16), 'impact', 0.36),
  at(600, 'pop', 0.6),
  at(690, 'whoosh-long', 0.5),

  // Context: the dashboard builds card by card, the thread links, memory.
  ...[-6, 16, 60, 90, 120, 150, 180, 210].map((s) => at(CONTEXT + s, 'pop', 0.8)),
  at(CONTEXT + 262, 'shimmer', 0.5),
  at(CONTEXT + 372, 'whoosh-long', 0.45),
  at(CONTEXT + 382, 'pop', 0.55),
  ...[420, 450, 480, 510].map((s) => at(CONTEXT + s, 'pop', 0.9)),
  at(CONTEXT + 668, 'whoosh-fast', 0.55),

  ...enumeration('know'),

  // Action: typing, send, specialists, answer, draft, the click on « Confirmer ».
  at(ACTION - 6, 'whoosh-long', 0.4),
  at(ACTION + 38, 'typing', 1.5),
  at(ACTION + 180, 'click', 1.1),
  at(ACTION + 188, 'whoosh-fast', 0.4),
  ...[240, 270, 300].map((s) => at(ACTION + s, 'pop', 1)),
  ...[332, 350, 368].map((s) => at(ACTION + s, 'tap', 1.6)),
  at(ACTION + 484, 'swish', 0.55),
  at(ACTION + 544, 'pop', 1),
  at(ACTION + 720, 'click', 1.4),
  at(ACTION + 728, 'success', 0.75),

  ...enumeration('act'),

  // Anticipate: LIA writes first, one tap, the run moves.
  at(ANTICIPATE - 4, 'whoosh-long', 0.4),
  at(ANTICIPATE + 62, 'notification', 0.85),
  at(ANTICIPATE + 180, 'tap', 2.2),
  at(ANTICIPATE + 180, 'click', 0.8),
  at(ANTICIPATE + 190, 'success', 0.65),

  ...enumeration('foresee'),

  // Devices: the two screens synchronise, four switches, four clicks.
  at(DEVICES + 40, 'shimmer', 0.4),
  at(DEVICES + 124, 'swish', 0.55),
  ...[132, 162, 192, 222].map((s) => at(DEVICES + s, 'click', 0.5)),

  ...enumeration('channels'),
  ...enumeration('circle'),
  ...enumeration('control'),

  // Linked: the bloom, one comet per beat, the collapse into the final hit.
  at(LINKED + 8, 'shimmer', 0.55),
  ...Array.from({ length: 8 }, (_, i) => at(LINKED + 120 + i * 30, 'swish', 0.3)),
  at(LINKED + 536, 'whoosh-long', 0.5),

  // Outro: the final hit, BIP, the underline.
  at(OUTRO, 'impact', 0.22),
  at(OUTRO + 26, 'pop', 0.55),
  at(OUTRO + 60, 'shimmer', 0.45),
];

/**
 * Short dips of the music under the three decisive gestures (send, confirm,
 * the tap on « Oui, vas-y »), so the click is felt without raising it into a
 * bang. Frames are the gesture; the dip starts just before and recovers fast.
 */
export const DUCKS: Array<{ frame: number; gain: number }> = [
  { frame: ACTION + 180, gain: 0.62 },
  { frame: ACTION + 720, gain: 0.55 },
  { frame: ANTICIPATE + 180, gain: 0.6 },
];
