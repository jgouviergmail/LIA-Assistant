import { describe, expect, it, vi } from 'vitest';
import { createRigWriter } from '../apply';
import { createEyeRig } from '../runtime';
import { NEUTRAL_CONTEXT } from '../direction';
import { restChannelValues } from '../channels';

describe('contextual physical prop delivery', () => {
  it('exposes only painted weather channels, caches the token set and forgets it on disposal', async () => {
    const root = document.createElement('span');
    const writer = createRigWriter(root);
    const mutations = vi.fn();
    const observer = new MutationObserver(mutations);
    observer.observe(root, { attributes: true, attributeFilter: ['data-weather-props'] });
    const values = {
      ...restChannelValues(),
      weatherRain: 0.7,
      weatherCold: 0.05,
      weatherNight: 0.02,
    };
    writer.write(values);
    expect(root.dataset.weatherProps).toBe('rain cold');
    writer.write({ ...values, weatherRain: 0.4 });
    expect(root.dataset.weatherProps).toBe('rain cold');
    await Promise.resolve();
    expect(mutations).toHaveBeenCalledTimes(1);
    expect(mutations.mock.calls[0][0]).toHaveLength(1);
    writer.dispose();
    expect(root.dataset.weatherProps).toBeUndefined();
    writer.write({ ...values, weatherSnow: 1 });
    expect(root.dataset.weatherProps).toBeUndefined();
    observer.disconnect();
  });

  it('announces the drop and the flake a scene carries, while they travel, like any other prop', () => {
    // The scene drives their path from 0 to their landing; at 0 they are not yet
    // there, and a slot nobody announces has no box (ADR-294, 2026-11-13).
    const root = document.createElement('span');
    const writer = createRigWriter(root);
    writer.write({ ...restChannelValues(), weatherDrop: 0.4 });
    expect(root.dataset.weatherProps).toBe('drop');
    writer.write({ ...restChannelValues(), weatherFlake: 1, weatherSnow: 1 });
    expect(root.dataset.weatherProps).toBe('snow flake');
    writer.write(restChannelValues());
    expect(root.dataset.weatherProps).toBeUndefined();
    writer.dispose();
  });

  it('announces the sky of an ordinary day like any other prop', () => {
    const root = document.createElement('span');
    const writer = createRigWriter(root);
    writer.write({ ...restChannelValues(), weatherSun: 1, weatherCloud: 0.4 });
    expect(root.dataset.weatherProps).toBe('sun cloud');
    writer.write({ ...restChannelValues(), weatherSun: 1 });
    expect(root.dataset.weatherProps).toBe('sun');
    writer.dispose();
  });

  it('combines verified weather and night throughout activity, with no prop loaded by an empty portrait', () => {
    const root = document.createElement('span');
    const writer = createRigWriter(root);
    const rig = createEyeRig({ reducedMotion: true });
    writer.write(rig.values());
    expect(root.dataset.weatherProps).toBeUndefined();
    rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'snow', dayPhase: 'night' });
    rig.settle();
    writer.write(rig.values());
    expect(root.dataset.weatherProps).toBe('snow night');
    rig.setContext({ ...NEUTRAL_CONTEXT, weather: 'snow', dayPhase: 'night', responding: true });
    rig.settle();
    writer.write(rig.values());
    expect(root.dataset.weatherProps).toBe('snow night');
    rig.setContext({ ...NEUTRAL_CONTEXT, dayPhase: 'night' });
    rig.settle();
    writer.write(rig.values());
    expect(root.dataset.weatherProps).toBe('night');
    writer.dispose();
  });
});
