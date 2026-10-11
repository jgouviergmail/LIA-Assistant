/** Store adapter; the rig itself remains pure and independently simulatable. */
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useLiveStore } from '@/stores/liveStore';
import { recentActivity } from '../activity';
import { NEUTRAL_CONTEXT, type ActingContext } from './direction';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { dayPhaseAt, weatherAt, weatherFlagsAt } from '../environment';

/** Environmental evidence has its own freshness, independent of activity and Psyche. */
function environmentContext(
  now: number
): Pick<ActingContext, 'weather' | 'weatherFlags' | 'dayPhase'> {
  const environment = useCompanionEnvironmentStore.getState().environment;
  return {
    weather: weatherAt(environment, now),
    weatherFlags: weatherFlagsAt(environment, now),
    dayPhase: environment ? dayPhaseAt(now, environment.timezone) : NEUTRAL_CONTEXT.dayPhase,
  };
}

export function liveActingContext(now: number): ActingContext {
  const psyche = usePsycheStore.getState();
  const signals = useEyesSignalsStore.getState();
  const activity = signals.liveActivity(now)?.family ?? null;
  const live = useLiveStore.getState().lastActivity;
  const record = live && live.at > (signals.lastActivity?.at ?? 0) ? live : signals.lastActivity;
  const recent = recentActivity(record, now);
  const task = {
    ...environmentContext(now),
    activity,
    responding: signals.liveReaction(now) !== null,
    recentFamily: recent?.family ?? null,
    recentWeight: recent?.weight ?? 0,
    accomplished: recent?.accomplished ?? false,
  };
  if (!psyche.enabled) return { ...NEUTRAL_CONTEXT, ...task };
  return {
    pleasure: psyche.moodPleasure,
    arousal: psyche.moodArousal,
    dominance: psyche.moodDominance,
    curiosity: psyche.driveCuriosity,
    engagement: psyche.driveEngagement,
    ...task,
  };
}
