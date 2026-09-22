import { expect, it } from 'vitest';
import { createEyeRig } from '../runtime';
import { NEUTRAL_CONTEXT } from '../direction';
import { ambientChannels } from '../ambient';
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

it('lets weather particles travel quietly, freezes them for reduced motion and retires them with work', () => {
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
  expect(rig.values().weatherSnow).toBe(0);
});

it('crossfades weather and yields to actual work without erasing the light of the room', () => {
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
  expect(rig.values().weatherCold).toBe(0);
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

it('gives the answer the full stage before returning to the weather', () => {
  const rig = createEyeRig({ reducedMotion: true });
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'heat', responding: true });
  rig.step(16);
  expect(rig.values().weatherHeat).toBe(0);
  rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'heat' });
  rig.step(16);
  expect(rig.values().weatherHeat).toBe(1);
});
