import { beforeEach, expect, it } from 'vitest';
import { liveActingContext } from '../live-context';
import { NEUTRAL_CONTEXT } from '../direction';
import { usePsycheStore as psyche } from '@/stores/psycheStore';
import { useEyesSignalsStore as signals } from '@/stores/eyesSignalsStore';
import { useLiveStore as live } from '@/stores/liveStore';
import type { Activity } from '../../activity';
import { useCompanionEnvironmentStore as environment } from '@/stores/companionEnvironmentStore';

const event: Activity = {
  version: 1,
  run_id: 'r',
  invocation_id: 'i',
  family: 'reading',
  intent: 'read',
  phase: 'finished',
  outcome: 'succeeded',
};
beforeEach(() => {
  psyche.getState().reset();
  signals.getState().reset();
  live.getState().reset();
  environment.getState().reset();
});

it('borrows fresh weather without replacing Psyche, then releases it at expiry', () => {
  const now = Date.parse('2026-09-21T12:00:00Z');
  environment.getState().setEnvironment({
    timezone: 'Pacific/Auckland',
    weather: {
      temperature_c: 9,
      condition_code: 'Rain',
      wind_speed_kmh: null,
      observed_at: new Date(now - 1000).toISOString(),
      expires_at: new Date(now + 1000).toISOString(),
    },
  });
  psyche.setState({ enabled: true, moodPleasure: 0.8 });
  expect(liveActingContext(now)).toMatchObject({
    weather: 'rain',
    weatherFlags: ['rain', 'cold'],
    dayPhase: 'night',
    pleasure: 0.8,
  });
  expect(liveActingContext(now + 1000)).toMatchObject({
    weather: null,
    weatherFlags: [],
    dayPhase: 'night',
    pleasure: 0.8,
  });
});

it('keeps concurrent environment evidence during real work and answer states independently of Psyche', () => {
  const now = Date.parse('2026-09-21T12:00:00Z');
  const observed = {
    timezone: 'Pacific/Auckland',
    weather: {
      temperature_c: 8,
      condition_code: 'Rain',
      wind_speed_kmh: 45,
      observed_at: new Date(now - 1000).toISOString(),
      expires_at: new Date(now + 1000).toISOString(),
    },
  };
  environment.getState().setEnvironment(observed);
  signals.getState().beginTurn('answer');
  signals
    .getState()
    .recordActivity({ ...event, phase: 'started', outcome: null }, 'answer', false, now);
  signals.getState().setReaction('joy', 1, 'none', now);
  const first = liveActingContext(now);
  expect(first).toMatchObject({
    activity: 'reading',
    responding: true,
    weather: 'rain',
    weatherFlags: ['rain', 'wind', 'cold'],
    dayPhase: 'night',
    pleasure: 0,
  });
  psyche.setState({ enabled: true, moodPleasure: 0.8 });
  const next = liveActingContext(now + 100);
  expect(next.weatherFlags).toBe(first.weatherFlags);
  expect(next.pleasure).toBe(0.8);
  expect(liveActingContext(now + 1000)).toMatchObject({
    weather: null,
    weatherFlags: [],
    dayPhase: 'night',
    activity: 'reading',
    responding: true,
  });
  expect(environment.getState().environment).toBe(observed);
});

it('uses neutral temperament when Psyche is disabled and expires answer release', () => {
  psyche.setState({ moodPleasure: 0.8, driveCuriosity: 0.9 });
  expect(liveActingContext(100)).toEqual(NEUTRAL_CONTEXT);
  psyche.getState().setEnabled(true);
  signals.getState().setReaction('joy', 1, 'none', 100);
  expect(liveActingContext(200)).toMatchObject({ pleasure: 0.8, curiosity: 0.9, responding: true });
  expect(liveActingContext(20_000).responding).toBe(false);
});

it('uses the most recent real voice or chat activity and never turns a lookup into an act', () => {
  signals.setState({ lastActivity: { event, at: 100 } });
  live.setState({ lastActivity: { event: { ...event, family: 'calculating' }, at: 200 } });
  expect(liveActingContext(300)).toMatchObject({
    recentFamily: 'calculating',
    accomplished: false,
  });
  signals.setState({
    lastActivity: { event: { ...event, intent: 'act', family: 'creating' }, at: 250 },
  });
  expect(liveActingContext(300)).toMatchObject({ recentFamily: 'creating', accomplished: true });
  expect(liveActingContext(7000).recentFamily).toBeNull();
});
