'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AppFrame } from './mockup/AppFrame';
import {
  AnticipateBackstage,
  AnticipateChat,
  CallBackstage,
  CallChat,
  CreateBackstage,
  CreateChat,
  OrchestrateBackstage,
  OrchestrateChat,
  type ActProps,
} from './mockup/acts';
import {
  REDUCED_MOTION_KINDS,
  SCENARIOS,
  type Scenario,
  type ScenarioId,
} from './mockup/scenarios';

/**
 * Animated hero conversation — a miniature of the real app cycling through
 * four acts (orchestrate, anticipate, call, create). While LIA "thinks", the
 * backstage glass pane reveals the actual orchestration instead of dead
 * waiting time; the response then lands back in the chat (see mockup/).
 *
 * Purely decorative: exposed as a single `role="img"`, every inner control is
 * a non-interactive span. Under `prefers-reduced-motion` act 1 renders
 * statically at its resolution moment.
 */

const CYCLE_FADE_MS = 600;

const ACTS: Record<ScenarioId, { Chat: React.FC<ActProps>; Backstage: React.FC<ActProps> }> = {
  orchestrate: { Chat: OrchestrateChat, Backstage: OrchestrateBackstage },
  anticipate: { Chat: AnticipateChat, Backstage: AnticipateBackstage },
  call: { Chat: CallChat, Backstage: CallBackstage },
  create: { Chat: CreateChat, Backstage: CreateBackstage },
};

/** True when `kind` sits inside any [from, to) window already reached. */
function inWindow(windows: [string, string][], reached: (kind: string) => boolean): boolean {
  return windows.some(([from, to]) => reached(from) && !reached(to));
}

/** Timeline engine: reveals scenario steps on schedule, then cycles. */
function useMockupTimeline(): {
  scenario: Scenario;
  reached: (kind: string) => boolean;
  fading: boolean;
  reducedMotion: boolean;
} {
  const [scenarioIndex, setScenarioIndex] = useState(0);
  const [stepCount, setStepCount] = useState(0);
  const [fading, setFading] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setReducedMotion(true);
      return;
    }

    let cancelled = false;
    let index = 0;

    const runCycle = () => {
      if (cancelled) return;
      const scenario = SCENARIOS[index];
      setScenarioIndex(index);
      setFading(false);
      setStepCount(0);
      timersRef.current = scenario.steps.map((step, i) =>
        setTimeout(() => setStepCount(i + 1), step.at)
      );
      timersRef.current.push(
        setTimeout(() => setFading(true), scenario.holdMs),
        setTimeout(() => {
          index = (index + 1) % SCENARIOS.length;
          runCycle();
        }, scenario.holdMs + CYCLE_FADE_MS)
      );
    };

    runCycle();
    return () => {
      cancelled = true;
      timersRef.current.forEach(clearTimeout);
    };
  }, []);

  const scenario = SCENARIOS[scenarioIndex];
  const visible = new Set(scenario.steps.slice(0, stepCount).map(step => step.kind));
  const reached = reducedMotion
    ? (kind: string) => REDUCED_MOTION_KINDS.has(kind)
    : (kind: string) => visible.has(kind);

  return { scenario, reached, fading, reducedMotion };
}

export function ChatMockup() {
  const { t } = useTranslation();
  const { scenario, reached, fading, reducedMotion } = useMockupTimeline();

  // Reduced motion pins the static frame to act 1 regardless of cycle state.
  const shown = reducedMotion ? SCENARIOS[0] : scenario;
  const act = ACTS[shown.id];

  const typing = !reducedMotion && reached('type') && !reached('user');
  const streaming = !reducedMotion && inWindow(shown.streamWindows, reached);
  const backstageOpen = !reducedMotion && reached('bs') && !reached('bs_end');
  const ticked = reached(shown.tokenbar.tickAt);
  const tokenbar = ticked ? shown.tokenbar.end : shown.tokenbar.start;

  return (
    <div
      className="relative w-full max-w-md mx-auto"
      role="img"
      aria-label={t('landing.chat_mockup.aria')}
    >
      {/* Ambient glow behind the card */}
      <div
        className="absolute -inset-6 rounded-[2rem] bg-gradient-to-br from-primary/25 via-violet-500/15 to-transparent blur-2xl"
        aria-hidden="true"
      />
      <div
        aria-hidden="true"
        className={`relative transition-opacity ${fading ? 'opacity-0 duration-500' : 'opacity-100 duration-300'}`}
      >
        <AppFrame
          chip={t(`landing.chat_mockup.${shown.chipKey}`)}
          tokenbar={tokenbar}
          ticked={ticked && !reducedMotion}
          typingText={typing ? t(`landing.chat_mockup.${shown.userKey}`) : null}
          voice={shown.voice}
          streaming={streaming}
          backstage={backstageOpen ? <act.Backstage reached={reached} /> : undefined}
        >
          <act.Chat reached={reached} />
        </AppFrame>
      </div>
    </div>
  );
}
