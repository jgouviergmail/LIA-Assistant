import { expect, it } from 'vitest';
import { createEyeRig } from '../runtime';
import { NEUTRAL_CONTEXT } from '../direction';
import { ambientChannels, weatherConditions } from '../ambient';
import type { WeatherFeeling } from '../../environment';

const weatherKinds: WeatherFeeling[] = [
  'rain',
  'storm',
  'cold',
  'freezing',
  'snow',
  'hot',
  'heat',
  'fog',
  'wind',
];

it('gives every condition a distinct motif rather than another opacity of the same prop', () => {
  const motifs = weatherKinds.map(weather =>
    Object.entries(ambientChannels(weather, 'noon', true))
      .filter(([key, weight]) => key.startsWith('weather') && weight > 0)
      .map(([key]) => key)
      .join(',')
  );
  expect(new Set(motifs).size).toBe(weatherKinds.length);
  for (const weather of weatherKinds) {
    const hidden = ambientChannels(weather, 'noon', false);
    expect(
      Object.entries(hidden).filter(([key, value]) => key.startsWith('weather') && value > 0)
    ).toEqual([]);
  }
});

it('lets weather particles travel quietly and freezes motion while keeping the condition visible during work', () => {
  const rig = createEyeRig();
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'snow' });
  for (let i = 0; i < 180; i++) rig.step(16);
  const fall = rig.values().ambientFall;
  for (let i = 0; i < 20; i++) rig.step(16);
  expect(rig.values().ambientFall).not.toBe(fall);
  expect(rig.values().ambientPulse).toBeGreaterThanOrEqual(0);
  expect(rig.values().ambientPulse).toBeLessThanOrEqual(1);
  rig.setReducedMotion(true);
  rig.step(16);
  const frozen = { ...rig.values() };
  for (let i = 0; i < 100; i++) rig.step(16);
  expect(rig.values()).toEqual(frozen);
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'snow', activity: 'reading' });
  rig.step(16);
  expect(rig.values().weatherSnow).toBe(1);
});

it('crossfades changed conditions while preserving the active prop and room light during work', () => {
  const rig = createEyeRig();
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'rain', dayPhase: 'evening' });
  expect(rig.values().weatherRain).toBe(0);
  for (let i = 0; i < 180; i++) rig.step(16);
  expect(rig.values().weatherRain).toBeGreaterThan(0.5);
  expect(rig.values().lightWarm).toBeGreaterThan(0.5);
  const before = rig.values().weatherRain;
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'cold', dayPhase: 'evening', activity: 'reading' });
  expect(rig.values().weatherRain).toBe(before);
  for (let i = 0; i < 300; i++) rig.step(16);
  expect(rig.values().weatherRain).toBe(0);
  expect(rig.values().weatherCold).toBe(0.65);
  expect(rig.values().lightWarm).toBeGreaterThan(0.5);
});

it('keeps reduced motion static and never lets the climate start a mouth performance', () => {
  const rig = createEyeRig({ reducedMotion: true });
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'wind', dayPhase: 'night' });
  rig.step(16);
  expect(rig.values().weatherWind).toBe(1);
  const frame = { ...rig.values() };
  for (let i = 0; i < 100; i++) rig.step(16);
  expect(rig.values()).toEqual(frame);
  expect(frame.ambientSway).toBe(0);
  expect(frame.mouthOpen).toBe(0);
});

it('retains the verified condition throughout an answer and removes it when that condition ends', () => {
  const rig = createEyeRig({ reducedMotion: true });
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'heat', responding: true });
  rig.step(16);
  expect(rig.values().weatherHeat).toBe(1);
  rig.setContext(NEUTRAL_CONTEXT);
  rig.step(16);
  expect(rig.values().weatherHeat).toBe(0);
});

it('keeps a cold scarf still until a head turn and lets its free end settle again', () => {
  const rig = createEyeRig();
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'cold' });
  for (let frame = 0; frame < 180; frame++) {
    rig.step(16);
    expect(rig.values().scarfTrail).toBe(0);
  }
  rig.setGaze({ x: 1, y: 0 });
  const trail = Array.from({ length: 180 }, () => {
    rig.step(16);
    return rig.values().scarfTrail;
  });
  expect(Math.min(...trail)).toBeLessThan(-0.08);
  expect(Math.min(...trail)).toBeGreaterThanOrEqual(-0.3);
  expect(Math.max(...trail)).toBe(0);
  expect(trail.at(-1)).toBe(0);

  rig.setGaze({ x: -1, y: 0 });
  for (let frame = 0; frame < 18; frame++) rig.step(16);
  expect(rig.values().scarfTrail).toBeGreaterThan(0.08);
  rig.setReducedMotion(true);
  expect(rig.values().scarfTrail).toBe(0);
});

it('wears every condition observed together, and the dominant one only when told no other', () => {
  // A cold rain is a scarf AND an umbrella: the dominant feeling names one.
  expect(weatherConditions('rain', ['rain', 'cold'])).toEqual(['rain', 'cold']);
  const worn = ambientChannels('rain', 'noon', true, ['rain', 'cold']);
  expect(worn.weatherRain).toBeGreaterThan(0);
  expect(worn.weatherCold).toBeGreaterThan(0);
  // A context that carries no flags is read by its dominant feeling...
  expect(weatherConditions('cold', [])).toEqual(['cold']);
  expect(weatherConditions('cold')).toEqual(['cold']);
  // ...and no weather at all is nothing, never undefined.
  expect(weatherConditions(null, [])).toEqual([]);
  expect(ambientChannels(null, 'noon', true).weatherCold).toBe(0);
});

it('draws the sky of an ordinary day by day only: a sun, and a cloud that passes on a cloudy day', () => {
  const clear = ambientChannels(null, 'noon', true, [], 'clear');
  expect(clear.weatherSun).toBe(1);
  expect(clear.weatherCloud).toBe(0);
  const cloudy = ambientChannels(null, 'afternoon', true, [], 'clouds');
  expect(cloudy.weatherSun).toBe(1);
  expect(cloudy.weatherCloud).toBe(1);
  // The night has its own crescent; a hidden ambience draws no sky either.
  for (const night of [
    ambientChannels(null, 'night', true, [], 'clear'),
    ambientChannels(null, 'noon', false, [], 'clouds'),
  ]) {
    expect(night.weatherSun).toBe(0);
    expect(night.weatherCloud).toBe(0);
  }
  expect(ambientChannels(null, 'noon', true).weatherSun).toBe(0);
});

it('moves the sky and what falls on the rig own clock: drops quicker than the fall, the drift slower', () => {
  const rig = createEyeRig();
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'rain', sky: 'clouds' });
  const wraps = { ambientFall: 0, ambientDrop: 0, ambientDrift: 0 };
  let previous = { ...rig.values() };
  for (let i = 0; i < 625; i++) {
    rig.step(16);
    const values = rig.values();
    for (const key of Object.keys(wraps) as (keyof typeof wraps)[])
      if (values[key] < previous[key] - 0.5) wraps[key] += 1;
    previous = { ...values };
  }
  // Ten seconds: three falls, nine drops, one drift at most.
  expect(wraps.ambientFall).toBe(3);
  expect(wraps.ambientDrop).toBe(9);
  expect(wraps.ambientDrift).toBeLessThanOrEqual(1);
  expect(rig.values().weatherSun).toBeGreaterThan(0.9);
  expect(rig.values().weatherCloud).toBeGreaterThan(0.9);
});

it('keeps the sky still under reduced motion, its drift parked like the fall', () => {
  const rig = createEyeRig({ reducedMotion: true });
  rig.setContext({ ...NEUTRAL_CONTEXT, sky: 'clear' });
  rig.step(16);
  expect(rig.values().weatherSun).toBe(1);
  const frame = { ...rig.values() };
  for (let i = 0; i < 100; i++) rig.step(16);
  expect(rig.values()).toEqual(frame);
  expect(frame.ambientDrift).toBe(0.5);
  expect(frame.ambientDrop).toBe(0.5);
});

it('turns the rays of a clear day: the sky alone keeps the clock running', () => {
  const rig = createEyeRig();
  rig.setContext({ ...NEUTRAL_CONTEXT, sky: 'clear' });
  for (let i = 0; i < 120; i++) rig.step(16);
  const drift = rig.values().ambientDrift;
  for (let i = 0; i < 60; i++) rig.step(16);
  expect(rig.values().ambientDrift).not.toBe(drift);
});
