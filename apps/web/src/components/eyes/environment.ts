/** Passive ambient context: observed weather and the account's civil clock. */
import { z } from '@/lib/zod';

export type WeatherFeeling =
  | 'rain'
  | 'storm'
  | 'snow'
  | 'fog'
  | 'wind'
  | 'cold'
  | 'freezing'
  | 'hot'
  | 'heat';
export type DayPhase = 'dawn' | 'morning' | 'noon' | 'afternoon' | 'evening' | 'night';

function validTimezone(timezone: string): boolean {
  try {
    new Intl.DateTimeFormat('en', { timeZone: timezone });
    return true;
  } catch {
    return false;
  }
}

const environmentSchema = z.object({
  timezone: z.string().max(100).refine(validTimezone),
  weather: z
    .object({
      temperature_c: z.number().min(-100).max(65),
      condition_code: z.string().min(1).max(32),
      wind_speed_kmh: z.number().min(0).max(500).nullable(),
      observed_at: z.iso.datetime({ offset: true }),
      expires_at: z.iso.datetime({ offset: true }),
    })
    .nullable(),
});

export type CompanionEnvironment = z.infer<typeof environmentSchema>;

export function parseEnvironment(input: unknown): CompanionEnvironment | null {
  const result = environmentSchema.safeParse(input);
  return result.success ? result.data : null;
}

const CONDITIONS: Readonly<Record<string, WeatherFeeling>> = {
  Rain: 'rain',
  Drizzle: 'rain',
  Thunderstorm: 'storm',
  Snow: 'snow',
  Fog: 'fog',
  Mist: 'fog',
  Haze: 'fog',
  Smoke: 'fog',
  Dust: 'fog',
  Sand: 'fog',
  Ash: 'fog',
  Squall: 'wind',
  Tornado: 'wind',
};

function freshWeatherAt(context: CompanionEnvironment | null, now: number) {
  const weather = context?.weather;
  if (!weather || !Number.isFinite(now)) return null;
  return now >= Date.parse(weather.observed_at) && now < Date.parse(weather.expires_at)
    ? weather
    : null;
}

function temperatureFeeling(temperature: number): WeatherFeeling | null {
  if (temperature < 0) return 'freezing';
  if (temperature < 10) return 'cold';
  if (temperature > 30) return 'heat';
  return temperature > 26 ? 'hot' : null;
}

// A bounded vocabulary gives at most 2^9 masks. Stable readonly arrays avoid
// retargeting the native rig merely because its context was sampled again.
const WEATHER_ORDER: readonly WeatherFeeling[] = [
  'rain',
  'storm',
  'snow',
  'fog',
  'wind',
  'cold',
  'freezing',
  'hot',
  'heat',
];
const weatherFlags = new Map<number, readonly WeatherFeeling[]>([[0, Object.freeze([])]]);
const weatherBit = (feeling: WeatherFeeling | null) =>
  feeling ? 1 << WEATHER_ORDER.indexOf(feeling) : 0;

function temperatureBits(temperature: number): number {
  const feeling = temperatureFeeling(temperature);
  const accompanying = feeling === 'freezing' ? 'cold' : feeling === 'heat' ? 'hot' : null;
  return weatherBit(feeling) | weatherBit(accompanying);
}

/** Independent evidence from one current observation; no forecast or invented climate. */
export function weatherFlagsAt(
  context: CompanionEnvironment | null,
  now: number
): readonly WeatherFeeling[] {
  const weather = freshWeatherAt(context, now);
  if (!weather) return weatherFlags.get(0)!;
  const condition = Object.hasOwn(CONDITIONS, weather.condition_code)
    ? CONDITIONS[weather.condition_code]
    : null;
  const wind = weather.wind_speed_kmh !== null && weather.wind_speed_kmh >= 40 ? 'wind' : null;
  const mask = weatherBit(condition) | weatherBit(wind) | temperatureBits(weather.temperature_c);
  const cached = weatherFlags.get(mask);
  if (cached) return cached;
  const flags = Object.freeze(WEATHER_ORDER.filter((_, index) => mask & (1 << index)));
  weatherFlags.set(mask, flags);
  return flags;
}

/** Legacy dominant intention retains condition → wind → temperature precedence. */
export function weatherAt(
  context: CompanionEnvironment | null,
  now: number
): WeatherFeeling | null {
  const flags = weatherFlagsAt(context, now);
  const dominant = flags[0] ?? null;
  if (dominant === 'cold' && flags.includes('freezing')) return 'freezing';
  if (dominant === 'hot' && flags.includes('heat')) return 'heat';
  return dominant;
}

// One cached formatter/result, not an unbounded timezone registry or an Intl
// allocation per animation frame. A context read may run several times a second.
let clockCache: { timezone: string; minute: number; hour: number } | null = null;

export function localHourAt(now: number, timezone: string): number {
  if (!Number.isFinite(now)) return 12;
  const minute = Math.floor(now / 60_000);
  if (clockCache?.timezone === timezone && clockCache.minute === minute) return clockCache.hour;
  const zone = validTimezone(timezone) ? timezone : 'UTC';
  const hour = Number(
    new Intl.DateTimeFormat('en', { timeZone: zone, hour: 'numeric', hourCycle: 'h23' }).format(now)
  );
  clockCache = { timezone, minute, hour };
  return hour;
}

export function dayPhaseAt(now: number, timezone: string): DayPhase {
  const hour = localHourAt(now, timezone);
  const bands: readonly [number, DayPhase][] = [
    [5, 'night'],
    [7, 'dawn'],
    [11, 'morning'],
    [14, 'noon'],
    [18, 'afternoon'],
    [22, 'evening'],
  ];
  return bands.find(([until]) => hour < until)?.[1] ?? 'night';
}
