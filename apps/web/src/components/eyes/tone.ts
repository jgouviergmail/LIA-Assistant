/**
 * The answer's REGISTER, and how hard the face plays it (ADR-253).
 *
 * The avatar used to pick its post-answer face from the psyche's dominant
 * emotion. That was the wrong instrument, and the production data says so
 * plainly: over fourteen consecutive turns the dominant emotion was
 * `enthusiasm` on thirteen of them, drifting by 0.02. A psyche is a TRAIT — it
 * moves slowly, on purpose — and an argmax over a near-constant vector is a
 * constant. Every answer earned the same face. The punctuation heuristic that
 * was supposed to cover the gap had nothing to say about nine of those fourteen
 * answers: no exclamation, no emoji, no code fence.
 *
 * So the model that writes the answer now declares its own register, in band,
 * and this module turns that declaration into a performance. Two halves:
 *
 *  - WHICH face: twelve registers, twelve genuinely different expressions. This
 *    is where most of the visible win lives — a technical answer stops grinning.
 *  - HOW HARD: the intensity is stage direction, and it is OVERPLAYED rather
 *    than reproduced. A cartoon that plays a 0.8 at 0.8 reads as a video call.
 *
 * The psyche keeps what it is good at: the IDLE mood family. A trait belongs on
 * the resting behaviour, not on a per-turn reaction.
 */

import type { EyeExpression, IdleGesture } from '@/components/eyes/expression-engine';

// =============================================================================
// The wire vocabulary (mirrors the backend's, and is validated against it)
// =============================================================================

export const TONE_REGISTERS = [
  'celebratory',
  'playful',
  'warm',
  'curious',
  'assured',
  'factual',
  'careful',
  'questioning',
  'surprised',
  'concerned',
  'apologetic',
  'weary',
] as const;

export type ToneRegister = (typeof TONE_REGISTERS)[number];

export const TONE_ACCENTS = ['none', 'wink', 'nod', 'tilt', 'sparkle', 'sigh'] as const;

export type ToneAccent = (typeof TONE_ACCENTS)[number];

/** What the `done` event carries under `expressivity`. */
export interface ToneAnnotation {
  register: ToneRegister;
  intensity: number;
  accent: ToneAccent;
}

const REGISTER_SET: ReadonlySet<string> = new Set(TONE_REGISTERS);
const ACCENT_SET: ReadonlySet<string> = new Set(TONE_ACCENTS);

/**
 * Validate an annotation off the wire.
 *
 * An unknown register yields null rather than a default: a face nobody designed
 * is worse than no reaction, and the caller already has a fallback that reads
 * the delivered text. The backend normalizes too — this is the second half of
 * the same contract, because the frontend is the one that would render the
 * nonsense.
 */
export function parseToneAnnotation(raw: unknown): ToneAnnotation | null {
  if (!raw || typeof raw !== 'object') return null;
  const value = raw as Record<string, unknown>;
  const register = typeof value.register === 'string' ? value.register : '';
  if (!REGISTER_SET.has(register)) return null;

  const rawIntensity = typeof value.intensity === 'number' ? value.intensity : NaN;
  const intensity = Number.isFinite(rawIntensity) ? Math.min(1, Math.max(0, rawIntensity)) : 0.5;
  const accent =
    typeof value.accent === 'string' && ACCENT_SET.has(value.accent) ? value.accent : 'none';

  return { register: register as ToneRegister, intensity, accent: accent as ToneAccent };
}

// =============================================================================
// Register → face
// =============================================================================

/**
 * The expression each register earns.
 *
 * Twelve registers, twelve distinct faces — that is the constraint the
 * vocabulary was built under, and it is the reason the list is not longer. Two
 * registers the avatar would play identically are one register with two names.
 */
export const REGISTER_EXPRESSIONS: Record<ToneRegister, EyeExpression> = {
  celebratory: 'excited',
  playful: 'joy',
  warm: 'tender',
  curious: 'attentive',
  assured: 'focused',
  factual: 'neutral',
  careful: 'thinking',
  questioning: 'question',
  surprised: 'surprise',
  concerned: 'worried',
  apologetic: 'sad',
  weary: 'tired',
};

/**
 * How much of the register's own energy the face is allowed to spend.
 *
 * A `celebratory` answer and a `careful` one do not deserve the same licence
 * even at the same declared intensity: one is meant to be seen from across the
 * room, the other is meant to be noticed. This is the per-register ceiling on
 * that licence, and it is what keeps "overplay" from becoming "shout".
 */
const REGISTER_LICENCE: Record<ToneRegister, number> = {
  celebratory: 1,
  playful: 0.95,
  warm: 0.7,
  curious: 0.7,
  assured: 0.6,
  factual: 0.35,
  careful: 0.5,
  questioning: 0.75,
  surprised: 1,
  concerned: 0.7,
  apologetic: 0.6,
  weary: 0.45,
};

// =============================================================================
// Amplitude — the overplay
// =============================================================================

/**
 * Amplitude bounds for the pose exaggeration.
 *
 * The previous emphasis, read from punctuation, spanned 0.94 to 1.21 on real
 * answers — a ±13 % scale on two channel groups, under an expression that never
 * changed. It was invisible by construction, and the owner said so before this
 * measurement existed.
 *
 * The band is wider now AND the signal that drives it actually varies. The
 * ceiling is a deliberate stop: past roughly 1.7 the pose channels start to
 * cross each other (a mouth wider than its own span, lids past their lashline)
 * and the face stops being a character and becomes a glitch.
 */
export const AMPLITUDE_MIN = 0.82;
export const AMPLITUDE_MAX = 1.7;

/**
 * The curve from declared intensity to played amplitude.
 *
 * Deliberately NOT linear. The interesting range of a declared intensity is its
 * middle — a model asked for [0, 1] clusters around 0.3-0.6 — so that middle is
 * where the amplitude has to move fastest. The exponent below puts the steep
 * part there and leaves the extremes as extremes.
 */
const INTENSITY_SHAPE = 0.72;

/**
 * How hard the face plays a tone.
 *
 * The register's licence caps what the intensity can buy, so a `factual` answer
 * declared at 1.0 is still a plain face delivered with conviction — not a
 * celebration. That asymmetry is the whole point: intensity says how strongly
 * the register came through, never which register it was.
 */
export function toneAmplitude(tone: ToneAnnotation): number {
  const shaped = Math.pow(Math.min(1, Math.max(0, tone.intensity)), INTENSITY_SHAPE);
  const licenced = shaped * REGISTER_LICENCE[tone.register];
  return AMPLITUDE_MIN + (AMPLITUDE_MAX - AMPLITUDE_MIN) * licenced;
}

// =============================================================================
// Accents — the one-shot beat on top
// =============================================================================

/**
 * The gesture an accent fires, if any.
 *
 * Every one of these is an EXISTING idle gesture, deliberately: the accent
 * vocabulary describes what the beat MEANS, and the rig already owns a tested
 * movement for each meaning. Inventing a fifth animation for "nod" when a
 * little hop already reads as acknowledgement would be a second mechanism
 * answering for one beat.
 *
 * `sparkle` is absent for the same reason, pointing the other way: it is an
 * accessory, not a movement, and it has its own channel.
 */
const ACCENT_GESTURES: Partial<Record<ToneAccent, IdleGesture>> = {
  wink: 'brow', // an eyebrow raised on one side: the universal "between us"
  nod: 'bounce', // a small hop — understood, agreed, done
  tilt: 'tilt',
  sigh: 'slow-blink',
};

/** The gesture for an accent, or null when the accent is not a movement. */
export function accentGesture(accent: ToneAccent): IdleGesture | null {
  return ACCENT_GESTURES[accent] ?? null;
}

/** Whether an accent should summon the delight accessory. */
export function accentSparkles(accent: ToneAccent): boolean {
  return accent === 'sparkle';
}

// =============================================================================
// The fallback: a register read from the answer itself
// =============================================================================

/**
 * What an answer's SHAPE says about its register, when no tag was declared.
 *
 * Measured on sixteen consecutive real turns: the in-band tone tag and the
 * psyche self-report tag — two independent mechanisms, the second in production
 * for months — were emitted on exactly the SAME two turns. An emission rate near
 * 12 % is a property of the response model, not of either feature, and a face
 * that reacts one turn in eight is a broken face.
 *
 * So this never returns nothing. It reads STRUCTURE — length, code fences,
 * punctuation density, emoji — and never words, so all six locales behave
 * identically (zh included, through the fullwidth marks). And it speaks the same
 * vocabulary as the declared tag, so there is ONE register table and ONE
 * amplitude curve rather than a parallel path with its own idea of a face.
 *
 * The declared tag stays the better signal: it knows the register the model
 * CHOSE, where this can only see how the answer was typed.
 */

/** Past this length an answer is expository: it is read, not exclaimed. */
const EXPOSITORY_LENGTH = 900;

// Emoji classes — deliberately short, high-precision lists. Punctuation and
// emoji are the only signals: no word matching, so all 6 locales behave
// identically (zh included via fullwidth ？ and ！).
const JOY_EMOJI = /[😀😃😄😁😊🙂😍🥰🤩🎉🎊✨🌟⭐❤🧡💛💚💙💜👍🥳💪🚀]/u;
const SAD_EMOJI = /[😢😭😞😔☹🙁💔😿]/u;
const SURPRISE_EMOJI = /[😮😲😯🤯]/u;

/** Strip fenced code blocks so their contents never drive punctuation cues. */
function withoutCodeFences(content: string): string {
  return content.replace(/```[\s\S]*?(?:```|$)/g, ' ');
}

/** Hesitation reads quieter whatever the register — an ellipsis is a pause. */
const HESITATION = /(\.\.\.|…)/;

/** Pick the register from the answer's shape. Order is priority. */
function registerFromShape(
  text: string,
  raw: string,
  source: { isError: boolean; hasArtifacts: boolean }
): ToneRegister {
  if (source.isError) return 'concerned';
  if (source.hasArtifacts) return 'celebratory';
  if (SAD_EMOJI.test(text)) return 'apologetic';
  if (SURPRISE_EMOJI.test(text)) return 'surprised';

  const bangs = (text.match(/[!！]/g) ?? []).length;
  if (bangs >= 2 || JOY_EMOJI.test(text)) return 'celebratory';
  if (/[?？]\s*$/.test(text.trim())) return 'questioning';
  if (bangs === 1) return 'playful';
  // `assured` is earned by a STRUCTURED delivery, not by brevity. A short
  // answer is just short: reading "the meeting is at 3pm" as determined put a
  // set jaw on a one-line reply.
  if (/```/.test(raw)) return 'assured';
  return 'factual';
}

/** How strongly each inferred register comes through, before modifiers. */
const SHAPE_INTENSITY: Record<ToneRegister, number> = {
  concerned: 0.7,
  celebratory: 0.62,
  apologetic: 0.6,
  surprised: 0.68,
  questioning: 0.55,
  playful: 0.45,
  assured: 0.42,
  factual: 0.32,
  // Not reachable from a shape today; declared so the record stays total and a
  // future cue cannot silently read as zero.
  warm: 0.5,
  curious: 0.5,
  careful: 0.45,
  weary: 0.4,
};

/**
 * Infer a tone annotation from the delivered answer.
 *
 * Never returns null: every completed turn earns an honest face. A plain
 * technical answer earns `factual`, which is the resting face played with
 * intent — not a grin nobody asked for.
 */
export function inferToneFromContent(source: {
  content: string;
  isError: boolean;
  hasArtifacts: boolean;
}): ToneAnnotation {
  const raw = source.content ?? '';
  const text = withoutCodeFences(raw);
  const register = registerFromShape(text, raw, source);

  let intensity = SHAPE_INTENSITY[register];
  if (HESITATION.test(text)) intensity -= 0.12;
  if (text.length > EXPOSITORY_LENGTH) intensity -= 0.06;

  return {
    register,
    intensity: Math.min(1, Math.max(0, intensity)),
    // The one accent a shape can honestly earn: something was actually made.
    accent: source.hasArtifacts ? 'sparkle' : 'none',
  };
}
