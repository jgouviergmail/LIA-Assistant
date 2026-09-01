/**
 * The answer's register, and how hard the face plays it (ADR-253).
 *
 * These tests exist because of a measurement, not a hunch. Over fourteen
 * consecutive production turns the psyche's dominant emotion was `enthusiasm`
 * on thirteen of them, drifting by 0.02, and the punctuation heuristic that was
 * supposed to cover the rest had nothing to say about nine of those answers. So
 * the avatar wore the same face after every single message.
 *
 * What is guarded here is the shape of the replacement: a closed vocabulary, a
 * total mapping, an amplitude that actually varies, and a register that caps
 * what intensity can buy.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  AMPLITUDE_MAX,
  AMPLITUDE_MIN,
  REGISTER_EXPRESSIONS,
  TONE_ACCENTS,
  TONE_REGISTERS,
  accentGesture,
  accentSparkles,
  inferToneFromContent,
  parseToneAnnotation,
  toneAmplitude,
  type ToneAnnotation,
  type ToneRegister,
} from '@/components/eyes/tone';
import { EYE_EXPRESSIONS } from '@/components/eyes/expression-engine';

function tone(overrides: Partial<ToneAnnotation> = {}): ToneAnnotation {
  return { register: 'factual', intensity: 0.5, accent: 'none', ...overrides };
}

describe('the wire contract', () => {
  it('accepts a well-formed annotation', () => {
    expect(parseToneAnnotation({ register: 'warm', intensity: 0.62, accent: 'nod' })).toEqual({
      register: 'warm',
      intensity: 0.62,
      accent: 'nod',
    });
  });

  it('REFUSES a register nobody designed, rather than inventing a face', () => {
    // The caller has a fallback that reads the delivered text; a face outside
    // the vocabulary has nothing behind it at all.
    expect(parseToneAnnotation({ register: 'smug', intensity: 0.9 })).toBeNull();
    expect(parseToneAnnotation({ intensity: 0.9 })).toBeNull();
    expect(parseToneAnnotation(null)).toBeNull();
    expect(parseToneAnnotation('warm')).toBeNull();
  });

  it('REPAIRS what is mechanically repairable and keeps the register', () => {
    // Same doctrine as the planner's parameter bounds: clamp what can be
    // clamped, and only fail on what cannot be fixed without inventing intent.
    expect(parseToneAnnotation({ register: 'warm', intensity: 7 })?.intensity).toBe(1);
    expect(parseToneAnnotation({ register: 'warm', intensity: -3 })?.intensity).toBe(0);
    expect(parseToneAnnotation({ register: 'warm' })?.intensity).toBe(0.5);
    expect(parseToneAnnotation({ register: 'warm', accent: 'shrug' })?.accent).toBe('none');
  });

  it('drops a NaN intensity to the middle instead of poisoning the amplitude', () => {
    expect(parseToneAnnotation({ register: 'warm', intensity: NaN })?.intensity).toBe(0.5);
  });
});

describe('register → face', () => {
  it('maps EVERY register, to an expression that actually exists', () => {
    const known = new Set<string>(EYE_EXPRESSIONS);
    for (const register of TONE_REGISTERS) {
      const expression = REGISTER_EXPRESSIONS[register];
      expect(expression, register).toBeDefined();
      expect(known.has(expression), `${register} → ${expression}`).toBe(true);
    }
  });

  it('gives each register a DISTINCT face — two names for one face is one register', () => {
    const faces = TONE_REGISTERS.map(r => REGISTER_EXPRESSIONS[r]);
    expect(new Set(faces).size).toBe(TONE_REGISTERS.length);
  });

  it('no longer ends every technical answer on a grin', () => {
    // The complaint this closed, in one assertion: the two registers a
    // technical exchange actually produces do not smile.
    expect(REGISTER_EXPRESSIONS.factual).toBe('neutral');
    expect(REGISTER_EXPRESSIONS.assured).toBe('focused');
  });
});

describe('amplitude — the overplay', () => {
  it('stays inside its band whatever it is handed', () => {
    for (const register of TONE_REGISTERS) {
      for (const intensity of [0, 0.25, 0.5, 0.75, 1]) {
        const value = toneAmplitude(tone({ register, intensity }));
        expect(value).toBeGreaterThanOrEqual(AMPLITUDE_MIN);
        expect(value).toBeLessThanOrEqual(AMPLITUDE_MAX);
      }
    }
  });

  it('rises with the declared intensity, on every register', () => {
    for (const register of TONE_REGISTERS) {
      const low = toneAmplitude(tone({ register, intensity: 0.2 }));
      const high = toneAmplitude(tone({ register, intensity: 0.9 }));
      expect(high, register).toBeGreaterThan(low);
    }
  });

  it('actually SPANS its band — the previous emphasis measured 0.94 to 1.21', () => {
    // That was a ±13 % scale on two channel groups, under an expression that
    // never changed: invisible by construction. A celebration and a weary
    // delivery must now be a different SIZE of face, not only a different one.
    const celebration = toneAmplitude(tone({ register: 'celebratory', intensity: 1 }));
    const weary = toneAmplitude(tone({ register: 'weary', intensity: 0.3 }));
    expect(celebration - weary).toBeGreaterThan(0.55);
  });

  it('lets the REGISTER cap what intensity can buy', () => {
    // A `factual` answer declared at full intensity is a plain face delivered
    // with conviction — never a celebration. Intensity says how strongly the
    // register came through; it never says which register it was.
    const factual = toneAmplitude(tone({ register: 'factual', intensity: 1 }));
    const celebratory = toneAmplitude(tone({ register: 'celebratory', intensity: 1 }));
    expect(factual).toBeLessThan(celebratory);
    expect(factual).toBeLessThan(1.25);
  });

  it('never falls below its floor even at a declared zero', () => {
    expect(toneAmplitude(tone({ register: 'weary', intensity: 0 }))).toBe(AMPLITUDE_MIN);
  });
});

describe('accents', () => {
  it('resolves every accent to an existing movement, or to nothing', () => {
    for (const accent of TONE_ACCENTS) {
      const gesture = accentGesture(accent);
      expect(gesture === null || typeof gesture === 'string').toBe(true);
    }
    expect(accentGesture('none')).toBeNull();
  });

  it('sends `sparkle` to the accessory channel, never to a gesture', () => {
    // One beat, one mechanism. A sparkle that was both a movement and an
    // accessory would be two systems answering for the same instant.
    expect(accentSparkles('sparkle')).toBe(true);
    expect(accentGesture('sparkle')).toBeNull();
    expect(accentSparkles('nod')).toBe(false);
  });
});

describe('the vocabulary is closed', () => {
  it('has a licence for every register (a missing one would read as zero)', () => {
    // The licence table is private, so this probes it through the only door
    // that exists: an amplitude above the floor at full intensity.
    for (const register of TONE_REGISTERS as readonly ToneRegister[]) {
      expect(toneAmplitude(tone({ register, intensity: 1 })), register).toBeGreaterThan(
        AMPLITUDE_MIN
      );
    }
  });
});

describe('the two halves of the contract agree', () => {
  // The backend normalizes and the frontend validates, against two copies of
  // the same list in two languages. A register added on one side only is a tag
  // the model is told to emit and the avatar silently drops — the exact class
  // of defect that has no symptom until someone films the face.
  const VOCABULARY = readFileSync(
    join(process.cwd(), '../api/src/domains/agents/expressivity/vocabulary.py'),
    'utf8'
  );

  function pythonTuple(name: string): string[] {
    const block = VOCABULARY.slice(VOCABULARY.indexOf(`${name}: Final[tuple[str, ...]] = (`));
    const body = block.slice(block.indexOf('('), block.indexOf(')'));
    return [...body.matchAll(/"([a-z]+)"/g)].map(m => m[1]);
  }

  it('declares the SAME registers on both sides, in the same order', () => {
    expect(pythonTuple('TONE_REGISTERS')).toEqual([...TONE_REGISTERS]);
  });

  it('declares the SAME accents on both sides', () => {
    expect(pythonTuple('TONE_ACCENTS')).toEqual([...TONE_ACCENTS]);
  });
});

describe('the fallback: a register inferred from the answer itself', () => {
  // MEASURED on 16 consecutive real turns of the dev instance: the in-band tag
  // and the psyche self-report tag — two independent mechanisms, the second in
  // production for months — were emitted on exactly the SAME two turns. An
  // emission rate near 12 % is a property of the response model, not of this
  // feature, and a face that only reacts one turn in eight is a broken face.
  //
  // So the fallback never returns nothing. It reads structure — length, code
  // fences, punctuation, emoji — never words, so all six locales behave
  // identically, and it speaks the SAME vocabulary as the declared tag: one
  // path, one register table, one amplitude curve.

  function infer(content: string, extra: { isError?: boolean; hasArtifacts?: boolean } = {}) {
    return inferToneFromContent({
      content,
      isError: extra.isError ?? false,
      hasArtifacts: extra.hasArtifacts ?? false,
    });
  }

  it('ALWAYS yields a register — never nothing', () => {
    for (const content of ['', 'Ok.', 'Voici la liste des taches du jour.', 'a'.repeat(3000)]) {
      const tone = infer(content);
      expect(TONE_REGISTERS).toContain(tone.register);
      expect(tone.intensity).toBeGreaterThanOrEqual(0);
      expect(tone.intensity).toBeLessThanOrEqual(1);
      expect(TONE_ACCENTS).toContain(tone.accent);
    }
  });

  it('owns a failure instead of smiling through it', () => {
    expect(infer('Impossible de joindre le service.', { isError: true }).register).toBe(
      'concerned'
    );
  });

  it('celebrates something actually delivered', () => {
    const tone = infer('Voici ton document.', { hasArtifacts: true });
    expect(tone.register).toBe('celebratory');
    expect(tone.accent).toBe('sparkle');
  });

  it('answers a trailing question with the questioning face', () => {
    expect(infer('Souhaitez-vous que je continue ?').register).toBe('questioning');
    expect(infer('还要继续吗？').register).toBe('questioning');
  });

  it('reads exclamation DENSITY, not the presence of one', () => {
    // One exclamation is punctuation; three is a mood.
    expect(infer('Parfait !').register).toBe('playful');
    expect(infer('Termine ! Tout est vert ! Bravo !').register).toBe('celebratory');
  });

  it('does not count punctuation written INSIDE a code block', () => {
    // `print("!!!")` is not enthusiasm.
    const tone = infer('Voici le script :\n```py\nprint("!!!")\nprint("!!!")\n```');
    expect(tone.register).not.toBe('celebratory');
  });

  it('treats a technical delivery as ASSURED, never as a celebration', () => {
    expect(infer('Voici la commande :\n```sh\ntask lint\n```').register).toBe('assured');
  });

  it('reads a long expository answer as FACTUAL and plays it small', () => {
    const long = infer('Le fonctionnement est le suivant. '.repeat(60));
    expect(long.register).toBe('factual');
    expect(toneAmplitude(long)).toBeLessThan(toneAmplitude(infer('Termine ! Bravo ! Super !')));
  });

  it('lets hesitation lower the intensity without changing the register', () => {
    const plain = infer('Le rendez-vous est a 14h.');
    const hesitant = infer('Le rendez-vous est a 14h... je crois.');
    expect(hesitant.register).toBe(plain.register);
    expect(hesitant.intensity).toBeLessThan(plain.intensity);
  });

  it('produces a face for EVERY answer shape, and not always the same one', () => {
    const shapes = [
      infer('Impossible.', { isError: true }),
      infer('Voici ton fichier.', { hasArtifacts: true }),
      infer('Tu veux que je continue ?'),
      infer('Fini ! Super ! Genial !'),
      infer('```sh\nls\n```'),
      infer('Le detail complet. '.repeat(80)),
    ];
    expect(new Set(shapes.map(s => s.register)).size).toBeGreaterThanOrEqual(5);
  });
});
