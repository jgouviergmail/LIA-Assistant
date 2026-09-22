import type { DayPhase, WeatherFeeling } from '../environment';
import type { ChannelKey, ChannelValues } from './channels';

type WeatherChannel = Extract<ChannelKey, `weather${string}`>;
const WEATHER: Record<WeatherFeeling, Partial<Record<WeatherChannel, number>>> = {
  rain: { weatherRain: 0.7 },
  storm: { weatherStorm: 1 },
  cold: { weatherCold: 0.65 },
  freezing: { weatherFreezing: 1 },
  snow: { weatherSnow: 1 },
  hot: { weatherHot: 0.85 },
  heat: { weatherHeat: 1 },
  fog: { weatherFog: 1 },
  wind: { weatherWind: 1 },
};
const LIGHT: Record<DayPhase, readonly [number, number]> = {
  dawn: [0.8, 0.1],
  morning: [0.35, 0],
  noon: [0, 0],
  afternoon: [0.18, 0],
  evening: [0.65, 0.25],
  night: [0, 1],
};

/** One ornament at a time. Light remains; props yield to the conversation. */
export function ambientChannels(
  weather: WeatherFeeling | null,
  phase: DayPhase,
  available: boolean
) {
  const [lightWarm, lightCool] = LIGHT[phase];
  return {
    weatherRain: 0,
    weatherStorm: 0,
    weatherCold: 0,
    weatherFreezing: 0,
    weatherSnow: 0,
    weatherHot: 0,
    weatherHeat: 0,
    weatherFog: 0,
    weatherWind: 0,
    weatherNight: available && !weather && phase === 'night' ? 0.7 : 0,
    lightWarm,
    lightCool,
    ...(available && weather ? WEATHER[weather] : {}),
  };
}

/** One rig clock, no independent CSS timer. Particles disappear at wraparound. */
export function ambientMotion(values: Readonly<ChannelValues>, now: number, reduced: boolean) {
  const weight = Math.max(
    values.weatherRain,
    values.weatherStorm,
    values.weatherCold,
    values.weatherFreezing,
    values.weatherSnow,
    values.weatherHot,
    values.weatherHeat,
    values.weatherFog,
    values.weatherWind
  );
  const moving = !reduced && weight > 0;
  // A fixed phase survives spring crossfades without speeding up or jumping.
  const fall = moving ? (now % 3200) / 3200 : 0.5;
  return {
    ambientSway: moving ? weight * (Math.sin(now / 1700) * 0.6 + Math.sin(now / 2900) * 0.25) : 0,
    ambientFall: fall,
    ambientPulse: Math.sin(Math.PI * fall) ** 2,
  };
}
