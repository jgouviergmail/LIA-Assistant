/** Asset selectors follow painted channels, including their native crossfade. */
import type { ChannelValues } from './channels';

const PROPS = {
  rain: 'weatherRain',
  storm: 'weatherStorm',
  cold: 'weatherCold',
  freezing: 'weatherFreezing',
  snow: 'weatherSnow',
  hot: 'weatherHot',
  heat: 'weatherHeat',
  fog: 'weatherFog',
  wind: 'weatherWind',
  night: 'weatherNight',
} as const;
export function createAmbientPropWriter(root: HTMLElement) {
  const entries = Object.entries(PROPS);
  let previous = 0;
  let active = true;
  return {
    write(values: Readonly<ChannelValues>) {
      if (!active) return;
      let mask = 0;
      for (let index = 0; index < entries.length; index++)
        if (values[entries[index][1]] > 0.02) mask |= 1 << index;
      if (mask === previous) return;
      previous = mask;
      const next = entries
        .filter((_, index) => mask & (1 << index))
        .map(([name]) => name)
        .join(' ');
      if (next) root.dataset.weatherProps = next;
      else delete root.dataset.weatherProps;
    },
    reset() {
      previous = -1;
      delete root.dataset.weatherProps;
    },
    dispose() {
      active = false;
      delete root.dataset.weatherProps;
    },
  };
}
