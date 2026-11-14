/**
 * Weather the character PLAYS, with what it already has.
 *
 * Until 2026-11-12 the weather was set down beside the face — a scarf, an
 * umbrella, three flakes — and the character did not react to it. The
 * reactions here:
 *
 *  - in the wind the eyes narrow (the head already leaned);
 *  - when something starts falling from the sky, the face greets it, once: the
 *    first drop of a rain lands on its head, the first flake of a snow is
 *    followed down to its nose, a storm is looked up at (2026-11-13);
 *  - in the cold it sneezes more than its share, and it shivers;
 *  - on a clear, mild day it turns its face to the sun.
 *
 * Observed weather only: no reading, no reaction (`environment.ts` is the one
 * door, and it never invents a climate).
 */

import { describe, expect, it } from 'vitest';

import { pickActingSketch, resolveActingProfile } from '../acting-profile';
import { NEUTRAL_CONTEXT, skyGlanceTapes, type ActingContext } from '../direction';
import { createLifeRandom } from '../life';
import { createEyeRig, type EyeRig } from '../runtime';
import { SKETCHES, SKY_FORGOTTEN_MS, createSketchClock, type SketchName } from '../sketches';
import { WEATHER_SCENES, arrivalScene } from '../weather-scenes';
import { blinkTapes } from '../gestures';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';
import type { WeatherFeeling } from '../../environment';

function under(weather: WeatherFeeling | null, more: Partial<ActingContext> = {}): ActingContext {
  return { ...NEUTRAL_CONTEXT, weather, weatherFlags: weather ? [weather] : [], ...more };
}

function run(rig: EyeRig, ms: number, each: (atMs: number) => void = () => undefined): void {
  for (let at = 16; at <= ms; at += 16) {
    rig.step(16);
    each(at);
  }
}

function resting(seed = 42, clock = createSketchClock()): EyeRig {
  return createEyeRig({
    initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
    lifeRandom: createLifeRandom(seed),
    sketchClock: clock,
  });
}

describe('in the wind', () => {
  it.each(RIG_EYE_STYLE_IDS)('narrows the eyes and lowers the brows on %s', styleId => {
    const settle = (weather: WeatherFeeling | null) => {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId, family: 'calm' },
        reducedMotion: true,
      });
      rig.setContext(under(weather));
      rig.step(16);
      return rig.values();
    };
    const calm = settle(null);
    const windy = settle('wind');
    expect(windy.syL).toBeLessThan(calm.syL * 0.9);
    expect(windy.syR).toBeLessThan(calm.syR * 0.9);
    expect(windy.browYL).toBeGreaterThan(calm.browYL);
    // Narrowed, not shut: the face still looks at the person.
    expect(windy.syL).toBeGreaterThan(calm.syL * 0.75);
    // The identity of the skin is untouched.
    expect(windy.rTopL).toBe(calm.rTopL);
    expect(windy.lidTopL).toBe(calm.lidTopL);
  });

  it('narrows them at work too, and never on a sleeping face', () => {
    const pose = (expression: 'focused' | 'sleep', weather: WeatherFeeling | null) => {
      const rig = createEyeRig({
        initial: { expression, styleId: 'billes', family: 'calm' },
        reducedMotion: true,
      });
      rig.setContext(under(weather, { activity: expression === 'focused' ? 'creating' : null }));
      rig.step(16);
      return rig.values().syL;
    };
    expect(pose('focused', 'wind')).toBeLessThan(pose('focused', null) * 0.93);
    expect(pose('sleep', 'wind')).toBe(pose('sleep', null));
  });

  it.each(['rain', 'snow', 'cold', 'fog', 'hot'] as const)('does not squint at %s', weather => {
    const settle = (feeling: WeatherFeeling | null) => {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
        reducedMotion: true,
      });
      rig.setContext(under(feeling));
      rig.step(16);
      return rig.values().syL;
    };
    expect(settle(weather)).toBe(settle(null));
  });
});

/**
 * Whether the face greets the weather it is given, within a second and a half,
 * read on the channels it drives: the eyes up at the sky, the first drop on its
 * head, a flake it follows down. One reading, whatever form the greeting takes.
 */
function greets(rig: EyeRig, context: ActingContext, windowMs = 1500): boolean {
  rig.setContext(context);
  let highest = 0;
  let prop = 0;
  run(rig, windowMs, () => {
    const values = rig.values();
    highest = Math.min(highest, values.gazeY);
    prop = Math.max(prop, values.weatherDrop, values.weatherFlake);
  });
  return highest < -0.45 || prop > 0.5;
}

/** A whole greeting plays out, so the next sky is read by a face at rest. */
const GREETING_MS = 4500;

describe('when something starts falling from the sky', () => {
  it('looks up at a storm, then back: one drop is no news in it', () => {
    const rig = resting();
    run(rig, 800);
    rig.setContext(under('storm'));
    let highest = 0;
    let prop = 0;
    run(rig, 1200, () => {
      highest = Math.min(highest, rig.values().gazeY);
      prop = Math.max(prop, rig.values().weatherDrop, rig.values().weatherFlake);
    });
    expect(highest).toBeLessThan(-0.45);
    expect(prop).toBe(0);
    // The head goes with the eyes: it is the sky it looks at.
    run(rig, 2200);
    expect(Math.abs(rig.values().gazeY)).toBeLessThan(0.05);
    expect(Math.abs(rig.values().headPitch)).toBeLessThan(0.08);
  });

  it.each([
    // A soft body ducks under the drop; a rigid casing cannot, its head nods.
    ['nimbo', 'bodySy'],
    ['billes', 'headPitch'],
  ] as const)(
    'feels the first drop of a rain on its head (%s: %s), looks up, then the umbrella opens',
    (characterId, flinchChannel) => {
      const clock = createSketchClock();
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
        characterId,
        lifeRandom: createLifeRandom(42),
        sketchClock: clock,
      });
      run(rig, 800);
      const atRest = rig.values()[flinchChannel];
      rig.setContext(under('rain'));
      let landedAt = -1;
      let rainWhenLanded = -1;
      let flinch = 0;
      let blink = 0;
      let highest = 0;
      let scene: string | null = null;
      run(rig, GREETING_MS, at => {
        scene ??= clock.scene;
        const values = rig.values();
        if (landedAt < 0 && values.weatherDrop >= 1) {
          landedAt = at;
          rainWhenLanded = values.weatherRain;
        }
        if (landedAt < 0) return;
        if (at <= landedAt + 400) {
          flinch = Math.max(flinch, Math.abs(values[flinchChannel] - atRest));
          blink = Math.max(blink, values.blinkL);
        }
        highest = Math.min(highest, values.gazeY);
      });
      expect(scene).toBe('weather-first-drop');
      expect(landedAt).toBeGreaterThan(0);
      // Nothing of the rain shows before the drop is felt.
      expect(rainWhenLanded).toBeLessThan(0.02);
      expect(flinch).toBeGreaterThan(flinchChannel === 'bodySy' ? 0.015 : 0.05);
      expect(blink).toBeGreaterThan(0.8);
      expect(highest).toBeLessThan(-0.45);
      // ...then the umbrella is there, and the drop is gone.
      expect(rig.values().weatherRain).toBeGreaterThan(0.5);
      expect(rig.values().weatherDrop).toBe(0);
    }
  );

  it('follows the first flake of a snow down to its nose, and smiles', () => {
    const clock = createSketchClock();
    const rig = resting(42, clock);
    run(rig, 800);
    const before = rig.values().mouthCurve;
    rig.setContext(under('snow'));
    let highestEarly = 0;
    let landedAt = -1;
    let gazeAtLanding = 0;
    let smile = before;
    let scene: string | null = null;
    run(rig, GREETING_MS, at => {
      scene ??= clock.scene;
      const values = rig.values();
      if (at <= 600) highestEarly = Math.min(highestEarly, values.gazeY);
      if (landedAt < 0 && values.weatherFlake >= 1) {
        landedAt = at;
        gazeAtLanding = values.gazeY;
      }
      if (landedAt >= 0) smile = Math.max(smile, values.mouthCurve);
    });
    expect(scene).toBe('weather-catch-flake');
    expect(highestEarly).toBeLessThan(-0.3);
    expect(landedAt).toBeGreaterThan(1500);
    // Down with it from the sky to the root of the nose, at the middle of the face.
    expect(gazeAtLanding - highestEarly).toBeGreaterThan(0.3);
    expect(Math.abs(gazeAtLanding)).toBeLessThan(0.25);
    expect(smile).toBeGreaterThan(before + 0.05);
    // The snow falls all along; the caught flake is gone.
    expect(rig.values().weatherSnow).toBeGreaterThan(0.5);
    expect(rig.values().weatherFlake).toBe(0);
  });

  it('comes back from the sky on its own soft return, before it lets go', () => {
    // A look held to the end of its tape would be handed to whatever spring
    // the expression has: a stare at the sky, then a drop.
    for (let seed = 1; seed <= 20; seed += 1) {
      const tapes = skyGlanceTapes(createLifeRandom(seed));
      for (const channel of ['gazeX', 'gazeY'] as const) {
        const tape = tapes.find(candidate => candidate.channel === channel);
        if (!tape) throw new Error(`no ${channel} tape`);
        const last = tape.keys[tape.keys.length - 1];
        expect(last.value).toBe(0);
        expect((tape.durationMs ?? 0) - last.atMs).toBeGreaterThanOrEqual(300);
        // ...and it is a look: up for well under a second and a half.
        expect(last.atMs).toBeLessThanOrEqual(1200);
      }
    }
  });

  it.each(['cold', 'freezing', 'wind', 'fog', 'hot', 'heat'] as const)(
    'has nothing to look up at in %s',
    weather => {
      const rig = resting();
      run(rig, 800);
      expect(greets(rig, under(weather))).toBe(false);
    }
  );

  it('is not replaced by a scene that comes due on the same frame', () => {
    // The rest has run its course just as the rain arrives: the greeting is this
    // frame's scene, and nothing drawn may take the face from it.
    const clock = { ...createSketchClock(), dueMs: Number.MAX_SAFE_INTEGER };
    const rig = resting(42, clock);
    run(rig, 800);
    // Due on the very next frame, the one that reads the rain.
    clock.dueMs = clock.restedMs + 8;
    rig.setContext(under('rain'));
    let scene: string | null = null;
    let drop = 0;
    run(rig, 900, () => {
      scene ??= clock.scene;
      drop = Math.max(drop, rig.values().weatherDrop);
    });
    expect(scene).toBe('weather-first-drop');
    expect(drop).toBeGreaterThan(0.5);
  });

  it('pursues the flake: on its way down the eyes never stop to wait for it', () => {
    // Steps would make the eyes hop from one place to the next, resting between:
    // the flake moves all along, and so do they (2026-11-13).
    const clock = createSketchClock();
    const rig = resting(42, clock);
    run(rig, 800);
    rig.setContext(under('snow'));
    let previous = rig.values().gazeY;
    let still = 0;
    let longestStill = 0;
    run(rig, 1800, at => {
      const gaze = rig.values().gazeY;
      if (at > 200) {
        still = Math.abs(gaze - previous) < 0.0015 ? still + 16 : 0;
        longestStill = Math.max(longestStill, still);
      }
      previous = gaze;
    });
    expect(longestStill).toBeLessThan(150);
  });

  it('greets once: the same rain on a face mounted again is no news', () => {
    const clock = createSketchClock();
    const first = resting(42, clock);
    first.setContext(under('rain'));
    run(first, GREETING_MS);
    // The companion is mounted again (another page), the rain has not stopped:
    // for a few seconds the new face knows no weather at all — the reading
    // has not come back — and that is not the rain stopping.
    const second = resting(43, clock);
    run(second, 4000);
    expect(greets(second, under('rain'))).toBe(false);
  });

  it('greets again when the sky changes, and when the rain comes back after a while', () => {
    // Resting scenes are kept out of this one: a quarter of an hour of rest
    // would play several, and a scene owns the face while it plays.
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
      sketchClock: { ...createSketchClock(), dueMs: Number.MAX_SAFE_INTEGER },
    });
    const greetsThenRests = (context: ActingContext) => {
      const greeted = greets(rig, context);
      run(rig, GREETING_MS);
      return greeted;
    };
    expect(greetsThenRests(under('rain'))).toBe(true);
    expect(greetsThenRests(under('snow'))).toBe(true);
    // The snow stops; the face has nothing to greet.
    expect(greetsThenRests(under(null))).toBe(false);
    // A reading that comes back at once was a reading being refreshed.
    expect(greetsThenRests(under('snow'))).toBe(false);
    // A sky that stayed empty for minutes was a sky that cleared.
    rig.setContext(under(null));
    run(rig, SKY_FORGOTTEN_MS + 1000);
    expect(greetsThenRests(under('snow'))).toBe(true);
  });

  it('counts each empty spell on its own: two short ones do not make a long one', () => {
    const rig = createEyeRig({
      initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
      lifeRandom: createLifeRandom(42),
      sketchClock: { ...createSketchClock(), dueMs: Number.MAX_SAFE_INTEGER },
    });
    expect(greets(rig, under('rain'))).toBe(true);
    run(rig, GREETING_MS);
    for (let spell = 0; spell < 2; spell += 1) {
      rig.setContext(under(null));
      run(rig, SKY_FORGOTTEN_MS * 0.6);
      // The same rain, back before it was forgotten: nothing to greet.
      expect(greets(rig, under('rain')), `after spell ${spell + 1}`).toBe(false);
    }
  });

  it('waits for the face to be free, and greets it then', () => {
    const rig = resting();
    run(rig, 500);
    // A turn is open: the face follows the text, the sky can wait.
    expect(greets(rig, under('rain', { attending: true }))).toBe(false);
    expect(greets(rig, under('rain'))).toBe(true);
  });

  it('greets nothing under reduced motion, nor on a face with no life of its own', () => {
    for (const options of [
      { reducedMotion: true, lifeRandom: createLifeRandom(1) },
      { reducedMotion: false },
    ]) {
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'billes', family: 'calm' },
        ...options,
      });
      expect(greets(rig, under('rain'))).toBe(false);
      // The weather is still shown: nothing holds the umbrella back.
      expect(rig.values().weatherRain).toBeGreaterThan(0.5);
    }
  });
});

describe('weather a face at rest lives', () => {
  /** The resting scenes a face plays in a minute, back to back, under one weather. */
  function restingScenes(context: ActingContext, seed = 7): SketchName[] {
    const clock = { ...createSketchClock(), dueMs: 300 };
    const rig = resting(seed, clock);
    rig.setContext(context);
    const played: SketchName[] = [];
    let last: SketchName | null = null;
    run(rig, 60_000, () => {
      if (clock.scene && clock.scene !== last) played.push(clock.scene);
      last = clock.scene;
      if (clock.dueMs > 300) clock.dueMs = 300;
    });
    expect(played.length).toBeGreaterThan(5);
    return played;
  }

  it('shivers in the cold', () => {
    const played = restingScenes(under('cold'));
    expect(played).toContain('weather-shiver');
    expect(played).not.toContain('weather-sun-bask');
  });

  it('turns its face to the sun on a clear, mild day', () => {
    const played = restingScenes(under(null, { sky: 'clear', dayPhase: 'noon' }));
    expect(played).toContain('weather-sun-bask');
    expect(played).not.toContain('weather-shiver');
  });

  it.each([
    ['a mild day with no sky', under(null)],
    ['a clear night', under(null, { sky: 'clear', dayPhase: 'night' })],
    ['a cloudy day', under(null, { sky: 'clouds', dayPhase: 'noon' })],
    ['a windy clear day', under('wind', { sky: 'clear', dayPhase: 'noon' })],
  ])('lives no weather on %s', (_, context) => {
    const played = restingScenes(context);
    for (const scene of WEATHER_SCENES) expect(played, scene).not.toContain(scene);
  });

  it('keeps its eyes closed in the sun: a spontaneous blink does not open them', () => {
    // Measured on the bench's paint (2026-11-13): a blink that came during the hold
    // opened the eyes the scene held shut, then let them close again.
    const rig = resting();
    run(rig, 500);
    rig.playScene('weather-sun-bask');
    run(rig, 1500);
    expect(rig.values().blinkL).toBeGreaterThan(0.8);
    rig.play(...blinkTapes());
    let lowest = 1;
    run(rig, 700, () => {
      lowest = Math.min(lowest, rig.values().blinkL, rig.values().blinkR);
    });
    expect(lowest).toBeGreaterThan(0.8);
  });

  it('still blinks when its eyes are its own, scene or not', () => {
    const rig = resting();
    run(rig, 500);
    rig.playScene('weather-shiver');
    run(rig, 200);
    rig.play(...blinkTapes());
    let closed = 0;
    run(rig, 400, () => {
      closed = Math.max(closed, rig.values().blinkL);
    });
    expect(closed).toBeGreaterThan(0.8);
  });

  it('draws a scene the weather offers as often as a favourite, never twice in a row', () => {
    const profile = resolveActingProfile('moss', 'billes');
    const draws = Array.from({ length: 2000 }, (_, index) =>
      pickActingSketch(profile, () => (index + 0.5) / 2000, [], true, ['cold'], ['weather-shiver'])
    );
    const count = (name: SketchName) => draws.filter(drawn => drawn === name).length;
    expect(count('weather-shiver')).toBe(count(profile.signature));
    // Offered nothing, it draws none.
    for (let index = 0; index < 2000; index += 1) {
      const drawn = pickActingSketch(profile, () => (index + 0.5) / 2000, [], true, ['cold']);
      expect(WEATHER_SCENES.some(scene => scene === drawn)).toBe(false);
    }
    for (let index = 0; index < 200; index += 1)
      expect(
        pickActingSketch(
          profile,
          () => index / 200,
          ['weather-shiver'],
          true,
          ['cold'],
          ['weather-shiver']
        )
      ).not.toBe('weather-shiver');
  });
});

describe('in the cold', () => {
  /** How often a profile draws a sneeze over an even spread of draws. */
  function sneezes(weather: readonly WeatherFeeling[]): number {
    const profile = resolveActingProfile('moss', 'billes');
    let count = 0;
    for (let index = 0; index < 2000; index += 1)
      if (pickActingSketch(profile, () => (index + 0.5) / 2000, [], true, weather) === 'sneeze')
        count += 1;
    return count;
  }

  it('sneezes more than its share, cold or freezing', () => {
    const mild = sneezes([]);
    expect(mild).toBeGreaterThan(0);
    expect(sneezes(['cold'])).toBeGreaterThan(mild * 2.5);
    expect(sneezes(['cold', 'freezing'])).toBeGreaterThan(mild * 2.5);
    // The dominant feeling alone, as a context that carries no flags gives it.
    expect(sneezes(['freezing'])).toBeGreaterThan(mild * 2.5);
    // ...and every other scene stays reachable: a cold is not a loop.
    const profile = resolveActingProfile('moss', 'billes');
    const drawn = new Set(
      Array.from({ length: 2000 }, (_, index) =>
        pickActingSketch(profile, () => (index + 0.5) / 2000, [], true, ['cold'])
      )
    );
    expect(drawn.size).toBe(SKETCHES.length);
  });

  it.each([['rain'], ['wind'], ['hot'], ['fog']] as const)('sneezes no more in %s', weather => {
    expect(sneezes([weather])).toBe(sneezes([]));
  });

  it('never sneezes twice in a row, cold or not', () => {
    const profile = resolveActingProfile('moss', 'billes');
    for (let index = 0; index < 200; index += 1)
      expect(pickActingSketch(profile, () => index / 200, ['sneeze'], true, ['freezing'])).not.toBe(
        'sneeze'
      );
  });

  it.each([
    ['with its flags', under('cold')],
    // The props read a context that carries no flags by its dominant feeling
    // (`weatherConditions`); a scarf with no sneeze would be two readings.
    ['by its dominant feeling alone', { ...NEUTRAL_CONTEXT, weather: 'cold' as const }],
    // A cold rain: the dominant feeling is the rain, the cold is in the flags.
    ['in a cold rain', under('rain', { weatherFlags: ['rain', 'cold'] })],
  ])('is what the rig draws from, %s: a cold face sneezes first more often', (_, cold) => {
    // The first scene of sixty faces, cold and mild, on the same seeds: the
    // rig hands the picker the weather it was given, or the two counts match.
    // A greeting of weather starting to fall is no draw: it is skipped. In the
    // cold the face also shivers, so a reaction to the cold is either scene.
    const firstColdReactions = (context: ActingContext) => {
      let reacted = 0;
      for (let seed = 1; seed <= 60; seed += 1) {
        const rig = resting(seed * 131);
        rig.setContext(context);
        let first: string | null = null;
        for (let at = 0; at < 45_000 && first === null; at += 16) {
          rig.step(16);
          const scene = rig.sketchClock().scene;
          if (scene && !isGreeting(scene)) first = scene;
        }
        expect(first, `seed ${seed}`).not.toBeNull();
        if (first === 'sneeze' || first === 'weather-shiver') reacted += 1;
      }
      return reacted;
    };
    const mild = firstColdReactions(under(null));
    const chilled = firstColdReactions(cold);
    expect(chilled).toBeGreaterThanOrEqual(8);
    expect(chilled).toBeGreaterThan(mild * 2);
  });
});

/** A scene that greets weather starting to fall, as opposed to one a resting face draws. */
function isGreeting(scene: string): boolean {
  return (['rain', 'snow'] as const).some(weather => arrivalScene(weather) === scene);
}
