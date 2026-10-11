import { describe, expect, it } from 'vitest';
import { EYE_EXPRESSIONS } from '../../expression-engine';
import type { WeatherFeeling } from '../../environment';
import { ambientChannels } from '../ambient';
import { NEUTRAL_CONTEXT } from '../direction';
import { createEyeRig } from '../runtime';
import { createRigWriter } from '../apply';
import { BODY_SKETCHES } from '../body-sketches';

const allWeather: readonly WeatherFeeling[] = [
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
const conditions = {
  ...NEUTRAL_CONTEXT,
  weather: 'rain' as const,
  weatherFlags: ['rain', 'cold', 'wind'] as const,
  dayPhase: 'night' as const,
};

describe('verified conditions own their accessories throughout the assistant activity', () => {
  it('composes every independent prop and night instead of selecting a single motif', () => {
    const channels = ambientChannels(null, 'night', true, allWeather);
    const visible = Object.entries(channels).filter(
      ([key, value]) => key.startsWith('weather') && value > 0
    );
    expect(visible).toHaveLength(10);
    expect(channels.weatherCold).toBe(0.65);
    expect(channels.weatherNight).toBe(0.7);
  });

  it('preserves exactly the active subset across every combination of independent conditions', () => {
    for (let mask = 0; mask < 1 << allWeather.length; mask++) {
      const flags = allWeather.filter((_, bit) => mask & (1 << bit));
      for (const phase of ['noon', 'night'] as const) {
        const channels = ambientChannels(null, phase, true, flags);
        for (const condition of allWeather) {
          const key =
            `weather${condition[0].toUpperCase()}${condition.slice(1)}` as keyof typeof channels;
          expect(channels[key] > 0).toBe(flags.includes(condition));
        }
        expect(channels.weatherNight > 0).toBe(phase === 'night');
      }
    }
  });

  it.each(EYE_EXPRESSIONS)(
    'retains cold/rain/wind/night while %s, reading and responding',
    expression => {
      const rig = createEyeRig({ reducedMotion: true });
      rig.setContext({ ...conditions, activity: 'reading', responding: true });
      rig.setPose({ expression, styleId: 'cozmo', family: 'calm' });
      rig.step(16);
      expect(rig.values().weatherCold).toBe(0.65);
      expect(rig.values().weatherRain).toBe(0.7);
      expect(rig.values().weatherWind).toBe(1);
      expect(rig.values().weatherNight).toBe(0.7);
    }
  );

  it.each(BODY_SKETCHES)(
    'keeps every verified accessory throughout %s and its return home',
    scene => {
      const root = document.createElement('span');
      const writer = createRigWriter(root);
      const rig = createEyeRig({
        initial: { expression: 'neutral', styleId: 'smiley', family: 'calm' },
        characterId: 'oscar',
        lifeRandom: () => 0.8,
      });
      rig.setContext(conditions);
      for (let i = 0; i < 240; i++) rig.step(16);
      rig.playScene(scene);
      expect(rig.isPerforming()).toBe(true);
      for (let i = 0; i < 500; i++) {
        rig.step(16);
        writer.write(rig.values());
        expect(root.dataset.weatherProps).toBe('rain cold wind night');
      }
      expect(rig.isPerforming()).toBe(false);
      writer.dispose();
    }
  );

  it('does not crossfade worn props away when the expression or task changes; only conditions remove them', () => {
    const root = document.createElement('span');
    const writer = createRigWriter(root);
    const rig = createEyeRig();
    rig.setContext(conditions);
    for (let i = 0; i < 240; i++) rig.step(16);
    for (const expression of ['thinking', 'sleep', 'speaking', 'surprise', 'neutral'] as const) {
      rig.setContext({ ...conditions, activity: 'reading', responding: true });
      rig.setPose({ expression, styleId: 'cozmo', family: 'calm' });
      for (let i = 0; i < 120; i++) {
        rig.step(16);
        writer.write(rig.values());
        expect(root.dataset.weatherProps).toBe('rain cold wind night');
      }
    }
    rig.setContext({ ...NEUTRAL_CONTEXT, weatherFlags: [] });
    for (let i = 0; i < 300; i++) rig.step(16);
    writer.write(rig.values());
    expect(root.dataset.weatherProps).toBeUndefined();
    writer.dispose();
  });
});
