import { describe, expect, it } from 'vitest';
import { dayPhaseAt, parseEnvironment, weatherAt, weatherFlagsAt } from '../environment';

const now = Date.parse('2026-09-21T12:00:00Z');
const payload = (temperature_c = 20, condition_code = 'Clear', wind_speed_kmh = 0) => ({
  timezone: 'Europe/Paris',
  weather: {
    temperature_c,
    condition_code,
    wind_speed_kmh,
    observed_at: new Date(now - 1000).toISOString(),
    expires_at: new Date(now + 1000).toISOString(),
  },
});

describe('weather is evidence, not a randomly selected decoration', () => {
  it.each([
    [-0.01, 'freezing'],
    [0, 'cold'],
    [9.99, 'cold'],
    [10, null],
    [26, null],
    [26.01, 'hot'],
    [30, 'hot'],
    [30.01, 'heat'],
  ] as const)('respects the requested temperature boundary at %s', (temperature, expected) => {
    expect(weatherAt(parseEnvironment(payload(temperature)), now)).toBe(expected);
  });
  it.each([
    ['Rain', 'rain'],
    ['Drizzle', 'rain'],
    ['Thunderstorm', 'storm'],
    ['Snow', 'snow'],
    ['Fog', 'fog'],
    ['Mist', 'fog'],
    ['Haze', 'fog'],
    ['Smoke', 'fog'],
    ['Dust', 'fog'],
    ['Sand', 'fog'],
    ['Ash', 'fog'],
    ['Squall', 'wind'],
    ['Tornado', 'wind'],
    ['Clouds', null],
    ['Unknown', null],
    ['__proto__', null],
  ] as const)('reads current %s without using a forecast', (condition, expected) => {
    expect(weatherAt(parseEnvironment(payload(20, condition)), now)).toBe(expected);
  });
  it('picks one weather intention and gives hazardous conditions precedence', () => {
    expect(weatherAt(parseEnvironment(payload(-5, 'Thunderstorm', 80)), now)).toBe('storm');
    expect(weatherAt(parseEnvironment(payload(28, 'Clear', 45)), now)).toBe('wind');
    expect(weatherAt(parseEnvironment(payload(20, 'Clear', 39)), now)).toBeNull();
  });
  it('expires at the observation deadline and rejects future observations', () => {
    const context = parseEnvironment(payload());
    expect(weatherAt(context, now + 1000)).toBeNull();
    expect(weatherAt(context, now - 2000)).toBeNull();
    expect(weatherAt(null, now)).toBeNull();
  });
  it.each([
    null,
    [],
    {},
    { timezone: 'Mars/Crater' },
    payload(NaN),
    payload(Infinity),
    payload(100),
  ])('rejects malformed context without animating made-up weather', input => {
    expect(parseEnvironment(input)).toBeNull();
  });
  it('accepts an explicitly absent weather observation', () => {
    expect(parseEnvironment({ timezone: 'UTC', weather: null })).toEqual({
      timezone: 'UTC',
      weather: null,
    });
  });
  it('accepts unavailable wind without inventing a gust', () => {
    const input = payload(8);
    expect(
      weatherAt(
        parseEnvironment({ ...input, weather: { ...input.weather, wind_speed_kmh: null } }),
        now
      )
    ).toBe('cold');
  });
});

describe('independent current weather conditions', () => {
  it('publishes cumulative weather tokens from the same observed snapshot', () => {
    expect(weatherFlagsAt).toBeTypeOf('function');
    const context = parseEnvironment(payload(8, 'Rain', 45));
    const flags = weatherFlagsAt(context, now);
    expect(flags).toEqual(['rain', 'wind', 'cold']);
    expect(Object.isFrozen(flags)).toBe(true);
    expect(weatherAt(context, now)).toBe('rain');
    expect(context?.weather).toEqual(payload(8, 'Rain', 45).weather);
  });

  it.each([
    [-5, 'Thunderstorm', 80, ['storm', 'wind', 'cold', 'freezing']],
    [32, 'Rain', 45, ['rain', 'wind', 'hot', 'heat']],
    [28, 'Fog', 0, ['fog', 'hot']],
    [8, 'Snow', 0, ['snow', 'cold']],
    [8, 'Squall', 45, ['wind', 'cold']],
    [8, '__proto__', 0, ['cold']],
  ] as const)('retains compatible evidence at %s°C/%s', (temperature, condition, wind, flags) => {
    expect(weatherFlagsAt(parseEnvironment(payload(temperature, condition, wind)), now)).toEqual(
      flags
    );
  });

  it('keeps cold and hot exclusive while retaining their additional extreme-condition props', () => {
    expect(weatherFlagsAt(parseEnvironment(payload(-5)), now)).toEqual(['cold', 'freezing']);
    expect(weatherAt(parseEnvironment(payload(-5)), now)).toBe('freezing');
    expect(weatherFlagsAt(parseEnvironment(payload(32)), now)).toEqual(['hot', 'heat']);
    expect(weatherAt(parseEnvironment(payload(32)), now)).toBe('heat');
    expect(weatherFlagsAt(parseEnvironment(payload(20, 'Clear', 39.99)), now)).toEqual([]);
    expect(weatherFlagsAt(parseEnvironment(payload(20, 'Clear', 40)), now)).toEqual(['wind']);
    expect(weatherFlagsAt(parseEnvironment(payload(0)), now)).toEqual(['cold']);
    expect(weatherFlagsAt(parseEnvironment(payload(10)), now)).toEqual([]);
    expect(weatherFlagsAt(parseEnvironment(payload(26)), now)).toEqual([]);
    expect(weatherFlagsAt(parseEnvironment(payload(30)), now)).toEqual(['hot']);
    const input = payload(8, 'Rain');
    expect(
      weatherFlagsAt(
        parseEnvironment({ ...input, weather: { ...input.weather, wind_speed_kmh: null } }),
        now
      )
    ).toEqual(['rain', 'cold']);
  });

  it('reuses canonical arrays when evidence and timestamps change without changing conditions', () => {
    const first = weatherFlagsAt(parseEnvironment(payload(8, 'Rain', 45)), now);
    const another = payload(9, 'Drizzle', 50);
    another.weather.observed_at = new Date(now - 500).toISOString();
    expect(weatherFlagsAt(parseEnvironment(another), now + 100)).toBe(first);
    expect(weatherFlagsAt(parseEnvironment(payload(8, 'Rain', 39)), now)).not.toBe(first);
    expect(weatherFlagsAt(null, now)).toBe(weatherFlagsAt(parseEnvironment(payload(20)), now));
  });

  it('drops all weather together at expiry or before observation while retaining civil night', () => {
    const context = parseEnvironment({ ...payload(8, 'Rain', 45), timezone: 'Pacific/Auckland' });
    expect(weatherFlagsAt(context, now - 1000)).toEqual(['rain', 'wind', 'cold']);
    expect(weatherFlagsAt(context, now - 1001)).toEqual([]);
    expect(weatherFlagsAt(context, now + 999)).toEqual(['rain', 'wind', 'cold']);
    expect(weatherFlagsAt(context, now + 1000)).toEqual([]);
    expect(dayPhaseAt(now + 1000, context?.timezone ?? 'UTC')).toBe('night');
    expect(weatherFlagsAt(null, now)).toEqual([]);
    expect(weatherFlagsAt(parseEnvironment({ timezone: 'UTC', weather: null }), now)).toEqual([]);
  });

  it.each([NaN, Infinity, -Infinity])('rejects invalid clock %s without invented props', clock => {
    expect(weatherFlagsAt(parseEnvironment(payload(8, 'Rain', 45)), clock)).toEqual([]);
  });
});

describe('local time of day', () => {
  it.each([
    [4, 'night'],
    [5, 'dawn'],
    [8, 'morning'],
    [12, 'noon'],
    [16, 'afternoon'],
    [20, 'evening'],
    [23, 'night'],
  ] as const)('reads local hour %s as %s', (hour, expected) => {
    expect(dayPhaseAt(Date.UTC(2026, 8, 21, hour), 'UTC')).toBe(expected);
  });
  it('uses the account timezone across midnight rather than the device timezone', () => {
    expect(dayPhaseAt(now, 'Pacific/Auckland')).toBe('night');
    expect(dayPhaseAt(now, 'America/Los_Angeles')).toBe('dawn');
  });
  it('reuses the current civil minute and degrades invalid clock inputs safely', () => {
    expect(dayPhaseAt(now, 'UTC')).toBe('noon');
    expect(dayPhaseAt(now + 999, 'UTC')).toBe('noon');
    expect(dayPhaseAt(now, 'unknown/zone')).toBe('noon');
    expect(dayPhaseAt(NaN, 'UTC')).toBe('noon');
  });
});
