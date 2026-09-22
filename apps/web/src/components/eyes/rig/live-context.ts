/** Store adapter; the rig itself remains pure and independently simulatable. */
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useLiveStore } from '@/stores/liveStore';
import { recentActivity } from '../activity';
import { NEUTRAL_CONTEXT, type ActingContext } from './direction';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { dayPhaseAt, weatherAt } from '../environment';

export function liveActingContext(now: number): ActingContext {
  const psyche = usePsycheStore.getState();
  const signals = useEyesSignalsStore.getState();
  const activity = signals.liveActivity(now)?.family ?? null;
  const live = useLiveStore.getState().lastActivity;
  const record = live && live.at > (signals.lastActivity?.at ?? 0) ? live : signals.lastActivity;
  const recent = recentActivity(record, now);
  const environment = useCompanionEnvironmentStore.getState().environment;
  const task = {
    weather: weatherAt(environment, now),
    dayPhase: environment ? dayPhaseAt(now, environment.timezone) : NEUTRAL_CONTEXT.dayPhase,
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
