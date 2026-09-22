/** Passive ambient context: observed weather and the account's civil clock. */
import { z } from 'zod';

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
};

export function weatherAt(
  context: CompanionEnvironment | null,
  now: number
): WeatherFeeling | null {
  const weather = context?.weather;
  if (!weather || now < Date.parse(weather.observed_at) || now >= Date.parse(weather.expires_at))
    return null;
  const condition = Object.hasOwn(CONDITIONS, weather.condition_code)
    ? CONDITIONS[weather.condition_code]
    : null;
  if (condition) return condition;
  if (weather.wind_speed_kmh !== null && weather.wind_speed_kmh >= 40) return 'wind';
  if (weather.temperature_c < 0) return 'freezing';
  if (weather.temperature_c < 10) return 'cold';
  if (weather.temperature_c > 30) return 'heat';
  return weather.temperature_c > 26 ? 'hot' : null;
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
