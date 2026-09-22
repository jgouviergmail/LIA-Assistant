/** The live inputs used by every companion skin, sampled on the host's clock. */
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { effectiveVoiceState } from '@/stores/liveStore';
import { useVoiceModeStore } from '@/stores/voiceModeStore';
import { usePsycheStore } from '@/stores/psycheStore';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import { localHourAt } from './environment';
import type { ExpressionInputs } from './expression-engine';

type LiveInputs = Pick<
  ExpressionInputs,
  | 'lastStepKind'
  | 'activity'
  | 'voiceState'
  | 'reaction'
  | 'notificationPing'
  | 'userTyping'
  | 'moodLabel'
  | 'hourOfDay'
>;

export function readCompanionSignals(now: number): LiveInputs {
  const signals = useEyesSignalsStore.getState();
  const psyche = usePsycheStore.getState();
  const activity = signals.liveActivity(now);
  const voice = effectiveVoiceState(useVoiceModeStore.getState().state);
  const environment = useCompanionEnvironmentStore.getState().environment;
  return {
    hourOfDay: environment ? localHourAt(now, environment.timezone) : new Date(now).getHours(),
    lastStepKind: activity ? 'tool' : signals.lastStepKind,
    activity: activity?.family ?? null,
    voiceState: voice === 'idle' && signals.audioPlaying ? 'speaking' : voice,
    reaction: signals.liveReaction(now),
    notificationPing: signals.isNotificationLive(now),
    userTyping: signals.isTypingLive(now),
    moodLabel: psyche.enabled ? psyche.moodLabel : null,
  };
}
