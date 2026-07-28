'use client';

/**
 * The rendered frame of the animated conversation mockup — everything between
 * the timeline state (scenario + reached) and the AppFrame chrome. Extracted
 * from the historical ChatMockup (UX P12) so the landing hero and the /demo
 * page render the exact same stage from the same timeline vocabulary (both
 * through InteractiveChatMockup since the hero transplant).
 */

import { useTranslation } from 'react-i18next';

import { AppFrame } from './AppFrame';
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
} from './acts';
import type { Scenario, ScenarioId } from './scenarios';

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

export interface MockupStageProps {
  scenario: Scenario;
  reached: (kind: string) => boolean;
  fading: boolean;
  reducedMotion: boolean;
}

/** One act of the mockup at its current timeline position. */
export function MockupStage({ scenario, reached, fading, reducedMotion }: MockupStageProps) {
  const { t } = useTranslation();
  const act = ACTS[scenario.id];

  const typing = !reducedMotion && reached('type') && !reached('user');
  const streaming = !reducedMotion && inWindow(scenario.streamWindows, reached);
  const backstageOpen = !reducedMotion && reached('bs') && !reached('bs_end');
  const ticked = reached(scenario.tokenbar.tickAt);
  const tokenbar = ticked ? scenario.tokenbar.end : scenario.tokenbar.start;

  return (
    <div
      aria-hidden="true"
      className={`relative transition-opacity ${fading ? 'opacity-0 duration-500' : 'opacity-100 duration-300'}`}
    >
      <AppFrame
        chip={t(`landing.chat_mockup.${scenario.chipKey}`)}
        tokenbar={tokenbar}
        ticked={ticked && !reducedMotion}
        typingText={typing ? t(`landing.chat_mockup.${scenario.userKey}`) : null}
        voice={scenario.voice}
        streaming={streaming}
        backstage={backstageOpen ? <act.Backstage reached={reached} /> : undefined}
      >
        <act.Chat reached={reached} />
      </AppFrame>
    </div>
  );
}
