import type { DayPhase, SkyCover, WeatherFeeling } from '../environment';
import type { ChannelKey, ChannelValues } from './channels';

type WeatherChannel = Extract<ChannelKey, `weather${string}`>;
export const WEATHER_COLD_MAX = 0.65;
const WEATHER: Record<WeatherFeeling, Partial<Record<WeatherChannel, number>>> = {
  rain: { weatherRain: 0.7 },
  storm: { weatherStorm: 1 },
  cold: { weatherCold: WEATHER_COLD_MAX },
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

const NO_CONDITIONS: readonly WeatherFeeling[] = [];

/**
 * The conditions a context observes: its flags, or — a context that carries
 * none — its dominant feeling. ONE reading for the props a face wears and
 * for what it plays: a scarf with no sneeze would be two readings.
 */
export function weatherConditions(
  weather: WeatherFeeling | null,
  weatherFlags?: readonly WeatherFeeling[]
): readonly WeatherFeeling[] {
  if (weatherFlags?.length) return weatherFlags;
  return weather ? [weather] : NO_CONDITIONS;
}

/**
 * Independent verified conditions compose; tasks and facial acting never hide a
 * worn prop. The sky of an ordinary day is drawn by day only — a sun, and a
 * cloud passing before it on a cloudy one — and never counts as a condition.
 */
export function ambientChannels(
  weather: WeatherFeeling | null,
  phase: DayPhase,
  enabled: boolean,
  weatherFlags?: readonly WeatherFeeling[],
  sky: SkyCover | null = null
) {
  const [lightWarm, lightCool] = LIGHT[phase];
  const daySky = enabled && phase !== 'night';
  const channels = {
    weatherRain: 0,
    weatherStorm: 0,
    weatherCold: 0,
    weatherFreezing: 0,
    weatherSnow: 0,
    weatherHot: 0,
    weatherHeat: 0,
    weatherFog: 0,
    weatherWind: 0,
    weatherNight: enabled && phase === 'night' ? 0.7 : 0,
    weatherSun: daySky && sky !== null ? 1 : 0,
    weatherCloud: daySky && sky === 'clouds' ? 1 : 0,
    lightWarm,
    lightCool,
  };
  if (enabled)
    for (const condition of weatherConditions(weather, weatherFlags))
      Object.assign(channels, WEATHER[condition]);
  return channels;
}

/** The fall's period. A drop falls three times in it, and the slow drift
 * — snow, clouds, a gust, the sun's rays — takes three of them. Whole ratios
 * keep every particle seamless where its sawtooth wraps. */
export const AMBIENT_FALL_MS = 3200;
export const AMBIENT_DROP_MS = AMBIENT_FALL_MS / 3;
export const AMBIENT_DRIFT_MS = AMBIENT_FALL_MS * 3;

/**
 * One rig clock, no independent CSS timer: every particle the sheet draws reads
 * one of these phases (sawtooths in [0, 1), parked at 0.5 when nothing moves)
 * and derives its own path from it. Props retain their visible coverage.
 */
export function ambientMotion(values: Readonly<ChannelValues>, now: number, reduced: boolean) {
  const weight = Math.max(
    values.weatherRain,
    values.weatherStorm,
    values.weatherFreezing,
    values.weatherSnow,
    values.weatherHot,
    values.weatherHeat,
    values.weatherFog,
    values.weatherWind,
    values.weatherSun,
    values.weatherCloud
  );
  const moving = !reduced && weight > 0;
  // A fixed phase survives spring crossfades without speeding up or jumping.
  const phase = (period: number) => (moving ? (now % period) / period : 0.5);
  const fall = phase(AMBIENT_FALL_MS);
  return {
    ambientSway: moving ? weight * (Math.sin(now / 1700) * 0.6 + Math.sin(now / 2900) * 0.25) : 0,
    ambientFall: fall,
    ambientPulse: Math.sin(Math.PI * fall) ** 2,
    ambientDrop: phase(AMBIENT_DROP_MS),
    ambientDrift: phase(AMBIENT_DRIFT_MS),
  };
}

/** Horizontal shear below the attachment line, drawn from lateral rig velocity. */
export function scarfTrail(cold: number, yawVelocity: number, rollVelocity: number): number {
  // Positive yaw carries the near cloth to the right. Positive roll carries
  // the lower cloth to the left. The free fabric follows each with a lag.
  const travel = rollVelocity * 0.009 - yawVelocity * 0.105;
  const amount = Math.min(1, Math.max(0, (Math.abs(travel) - 0.025) / 0.325));
  if (amount === 0 || cold <= 0) return 0;
  const eased = amount * amount * (3 - 2 * amount);
  return Math.sign(travel) * 0.3 * eased * Math.min(1, cold / WEATHER_COLD_MAX);
}
