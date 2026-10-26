/** Native civil/weather semantics, anchored to server time instead of device time. */
import {
  dayPhaseAt,
  parseEnvironment,
  weatherFlagsAt,
  type CompanionEnvironment,
  type DayPhase,
} from '@/components/eyes/environment';

export interface WorldEnvironmentAnchor {
  context: CompanionEnvironment;
  serverTime: number;
  receivedAt: number;
}
export interface Atmosphere {
  sunny?: boolean;
  phase: DayPhase | 'unknown';
  weather: 'neutral' | 'rain' | 'snow' | 'fog';
  time: number | null;
  timezone: string | null;
}
export const NEUTRAL_ATMOSPHERE: Atmosphere = Object.freeze({
  phase: 'unknown',
  weather: 'neutral',
  time: null,
  timezone: null,
});

export function readWorldEnvironment(
  value: unknown,
  receivedAt: number
): WorldEnvironmentAnchor | null {
  const context = parseEnvironment(value);
  if (
    !context ||
    !value ||
    typeof value !== 'object' ||
    !('server_time' in value) ||
    typeof value.server_time !== 'number' ||
    !Number.isFinite(value.server_time) ||
    value.server_time < 0 ||
    !Number.isFinite(receivedAt)
  )
    return null;
  return { context, serverTime: value.server_time * 1000, receivedAt };
}
export function atmosphereAt(anchor: WorldEnvironmentAnchor | null, now: number): Atmosphere {
  if (!anchor || !Number.isFinite(now) || now - anchor.receivedAt > 30 * 60_000)
    return NEUTRAL_ATMOSPHERE;
  const time = anchor.serverTime + Math.max(0, now - anchor.receivedAt);
  const flags = weatherFlagsAt(anchor.context, time);
  const weather =
    flags.includes('rain') || flags.includes('storm')
      ? 'rain'
      : flags.includes('snow')
        ? 'snow'
        : flags.includes('fog')
          ? 'fog'
          : 'neutral';
  return {
    sunny:
      anchor.context.weather?.condition_code === 'Clear' &&
      time >= Date.parse(anchor.context.weather.observed_at) &&
      time < Date.parse(anchor.context.weather.expires_at),
    phase: dayPhaseAt(time, anchor.context.timezone),
    weather,
    time,
    timezone: anchor.context.timezone,
  };
}
