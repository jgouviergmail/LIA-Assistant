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
