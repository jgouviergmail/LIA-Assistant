/**
 * Weather the character LIVES (ADR-294, follow-up of 2026-11-13): the four scenes
 * the owner chose on the bench — the first drop, the caught flake, the shiver, the
 * sun on the face — and the rules that decide when the weather offers them.
 *
 * The drop and the flake are props the sheet draws from two channels the scenes
 * drive; what matters here is that each meets the face on its own beat.
 */
import { describe, expect, it } from 'vitest';

import type { WeatherFeeling } from '../../environment';
import type { ChannelKey } from '../channels';
import { isLimbChannel } from '../limbs';
import { SKETCHES, isSketchName, sketchTapes } from '../sketches';
import { tapeDurationMs, tapeTargetAt, type Tape } from '../tape';
import {
  DROP_LANDS_MS,
  FLAKE_LANDS_MS,
  RAIN_HELD_MS,
  WEATHER_SCENES,
  arrivalScene,
  carriesProp,
  isChilled,
  restingWeatherScenes,
  weatherSceneTapes,
} from '../weather-scenes';

function only(tapes: readonly Tape[], channel: ChannelKey): Tape {
  const found = tapes.filter(tape => tape.channel === channel);
  expect(found, channel).toHaveLength(1);
  return found[0];
}

describe('when the weather starts to fall', () => {
  it('greets rain with the first drop and snow with a caught flake; a storm is looked at', () => {
    expect(arrivalScene('rain')).toBe('weather-first-drop');
    expect(arrivalScene('snow')).toBe('weather-catch-flake');
    // One drop is no news in a storm: the face looks up at it instead.
    expect(arrivalScene('storm')).toBeNull();
    for (const feeling of ['cold', 'freezing', 'wind', 'fog', 'hot', 'heat'] as const)
      expect(arrivalScene(feeling), feeling).toBeNull();
  });

  it('lands the drop on the flinch: the face feels it before the rain shows', () => {
    const tapes = weatherSceneTapes('weather-first-drop');
    const drop = only(tapes, 'weatherDrop');
    expect(tapeTargetAt(drop, 0)).toBe(0);
    expect(tapeTargetAt(drop, DROP_LANDS_MS / 2)).toBeGreaterThan(0);
    expect(tapeTargetAt(drop, DROP_LANDS_MS / 2)).toBeLessThan(1);
    expect(tapeTargetAt(drop, DROP_LANDS_MS)).toBe(1);
    // ...and it is gone once it has splashed: no prop is left on the head.
    expect(drop.keys[drop.keys.length - 1].value).toBe(0);
    expect(tapeDurationMs(drop)).toBeLessThan(DROP_LANDS_MS + 400);

    const flinch = only(tapes, 'bodySy');
    expect(flinch.keys[0].atMs).toBe(DROP_LANDS_MS);
    expect(flinch.keys[0].value).toBeLessThan(1);
    const blink = only(tapes, 'blinkL');
    expect(tapeTargetAt(blink, DROP_LANDS_MS)).toBe(1);

    // The cloud and the umbrella come once the drop has been felt, as the face looks up.
    const rain = only(tapes, 'weatherRain');
    expect(tapeTargetAt(rain, 0)).toBe(0);
    expect(tapeTargetAt(rain, DROP_LANDS_MS + 100)).toBe(0);
    expect(RAIN_HELD_MS).toBeGreaterThan(DROP_LANDS_MS);
    expect(tapeDurationMs(rain)).toBe(RAIN_HELD_MS);
    const up = only(tapes, 'gazeY');
    expect(Math.min(...up.keys.map(key => key.value))).toBeLessThan(-0.5);
    expect(up.keys.find(key => key.value < -0.5)?.atMs).toBeGreaterThan(DROP_LANDS_MS);
  });

  it('settles the flake on the nose as the eyes come down to it, then blinks and smiles', () => {
    const tapes = weatherSceneTapes('weather-catch-flake');
    const flake = only(tapes, 'weatherFlake');
    expect(tapeTargetAt(flake, 0)).toBe(0);
    expect(tapeTargetAt(flake, FLAKE_LANDS_MS)).toBe(1);
    expect(flake.keys[flake.keys.length - 1].value).toBe(0);

    const gaze = only(tapes, 'gazeY');
    // It starts up where the flake comes from, and comes down with it to the root of
    // the nose — the one place on every face where it covers no eye, brow or mouth.
    const start = tapeTargetAt(gaze, 0) ?? 0;
    const landing = tapeTargetAt(gaze, FLAKE_LANDS_MS) ?? 0;
    expect(start).toBeLessThan(-0.5);
    expect(landing - start).toBeGreaterThan(0.45);
    expect(Math.abs(landing)).toBeLessThan(0.25);
    const blink = only(tapes, 'blinkL');
    expect(blink.keys[0].atMs).toBeGreaterThan(FLAKE_LANDS_MS);
    expect(blink.keys[0].value).toBe(1);
    const smile = only(tapes, 'mouthCurve');
    expect(smile.keys[0].atMs).toBeGreaterThan(FLAKE_LANDS_MS);
    expect(smile.keys[0].value).toBeGreaterThan(0.1);
    // The snow itself is not held back: one flake is caught among the others.
    expect(tapes.some(tape => tape.channel === 'weatherSnow')).toBe(false);
  });
});

describe('the weather a face at rest may live', () => {
  const offered = (
    conditions: readonly WeatherFeeling[],
    sky: 'clear' | 'clouds' | null,
    phase: 'dawn' | 'morning' | 'noon' | 'afternoon' | 'evening' | 'night'
  ) => restingWeatherScenes(conditions, sky, phase);

  it('shivers in the cold, whatever the sky', () => {
    expect(offered(['cold'], null, 'noon')).toEqual(['weather-shiver']);
    expect(offered(['freezing'], 'clear', 'noon')).toEqual(['weather-shiver']);
    expect(offered(['cold', 'wind'], null, 'night')).toEqual(['weather-shiver']);
  });

  it.each(['dawn', 'morning', 'noon', 'afternoon', 'evening'] as const)(
    'turns its face to a mild clear sky in the %s',
    phase => {
      expect(offered([], 'clear', phase)).toEqual(['weather-sun-bask']);
    }
  );

  it('has no sun to turn to at night, under clouds, or in a weather it feels', () => {
    expect(offered([], 'clear', 'night')).toEqual([]);
    expect(offered([], 'clouds', 'noon')).toEqual([]);
    expect(offered([], null, 'noon')).toEqual([]);
    for (const feeling of ['wind', 'hot', 'heat', 'fog', 'rain', 'storm', 'snow'] as const)
      expect(offered([feeling], 'clear', 'noon'), feeling).toEqual([]);
  });

  it('reads the cold from the conditions alone', () => {
    expect(isChilled(['cold'])).toBe(true);
    expect(isChilled(['wind', 'freezing'])).toBe(true);
    expect(isChilled([])).toBe(false);
    expect(isChilled(['hot', 'wind', 'rain'])).toBe(false);
  });
});

describe('every weather scene', () => {
  it('is a named scene of the rig, outside the catalogue a face draws from at any time', () => {
    for (const name of WEATHER_SCENES) {
      expect(isSketchName(name), name).toBe(true);
      expect(SKETCHES, name).not.toContain(name);
      expect(sketchTapes(name), name).toEqual(weatherSceneTapes(name));
    }
  });

  it('is never warped when its prop meets the face on one beat', () => {
    expect(carriesProp('weather-first-drop')).toBe(true);
    expect(carriesProp('weather-catch-flake')).toBe(true);
    expect(carriesProp('weather-shiver')).toBe(false);
    expect(carriesProp('weather-sun-bask')).toBe(false);
    expect(carriesProp('sneeze')).toBe(false);
    expect(carriesProp('nothing')).toBe(false);
  });

  it.each(WEATHER_SCENES)('%s plays on every character and is a piece, not a beat', name => {
    const tapes = weatherSceneTapes(name);
    const length = Math.max(...tapes.map(tapeDurationMs));
    expect(length).toBeGreaterThanOrEqual(1500);
    expect(length).toBeLessThanOrEqual(5000);
    // No limb: it needs no arm, so no character loses half of it.
    expect(tapes.filter(tape => isLimbChannel(tape.channel))).toEqual([]);
    for (const tape of tapes)
      expect(Number.isFinite(tapeDurationMs(tape)), tape.channel).toBe(true);
  });
});
