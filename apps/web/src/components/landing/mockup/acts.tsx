'use client';

import { useTranslation } from 'react-i18next';
import { CalendarCheck, Phone } from 'lucide-react';
import { AssistantRow, UserBubble, WaitBubble } from './bubbles';
import { AccentCard, DraftCard, HydrationWidget, WeatherCard } from './cards';
import {
  Backstage,
  BsCall,
  BsChip,
  BsFan,
  BsForge,
  BsGate,
  BsNote,
  BsQuery,
  BsRail,
  BsSparkLink,
  BsStem,
} from './backstage';
import { BACKSTAGE_COSTS, SCENARIO_FOOTERS } from './scenarios';

/**
 * The four acts of the hero animation. Each act exposes a chat renderer
 * (the conversation rows revealed so far) and a backstage renderer (the
 * glass-pane figure shown while LIA works). Both derive everything from
 * `reached(kind)` — the timeline engine lives in ChatMockup.tsx.
 *
 * Act structure (why these four): one sentence fanning out to parallel
 * agents held by the approval gate, a self-connecting initiative, a real
 * outbound phone call, and a skill mini-app forged in-chat — together they
 * cover orchestration, control, memory, proactivity, real-world reach,
 * creation, voice and cost transparency.
 */

export interface ActProps {
  reached: (kind: string) => boolean;
}

const TK = 'landing.chat_mockup';

/** Shared translation shorthand for act renderers. */
function useMockupT(): (suffix: string) => string {
  const { t } = useTranslation();
  return (suffix: string) => t(`${TK}.${suffix}`);
}

// ---------------------------------------------------------------- Act 1 —
// "She orchestrates": memory + parallel agents + HITL gate + character.

export function OrchestrateChat({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <>
      {reached('user') && <UserBubble text={tm('s1_user')} />}
      {reached('wait') && !reached('hitl') && <WaitBubble text={tm('s1_wait')} />}
      {reached('hitl') && (
        <AssistantRow variant="hitl">
          {tm('s1_hitl')}
          <DraftCard
            to={tm('s1_draft_to')}
            subject={tm('s1_draft_subject')}
            quote={tm('s1_draft_quote')}
          />
        </AssistantRow>
      )}
      {reached('approve') && <UserBubble text={tm('s1_approve')} />}
      {reached('done') && (
        <AssistantRow variant="success" footer={SCENARIO_FOOTERS.orchestrate}>
          {tm('s1_done')}
        </AssistantRow>
      )}
    </>
  );
}

export function OrchestrateBackstage({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <Backstage
      label={tm('backstage_label')}
      cost={BACKSTAGE_COSTS.orchestrate}
      costLabel={tm('bs_cost_live')}
    >
      <BsQuery text={tm('s1_bs_query')} />
      <BsFan direction="split" />
      <div className="flex w-full justify-center gap-1.5">
        <BsChip
          label={tm('s1_bs_c1')}
          sub={tm('s1_bs_c1_sub')}
          state={reached('bs_c1') ? 'done' : 'run'}
        />
        <BsChip
          label={tm('s1_bs_c2')}
          sub={tm('s1_bs_c2_sub')}
          state={reached('bs_c2') ? 'done' : 'run'}
        />
        <BsChip label={tm('s1_bs_c3')} sub={tm('s1_bs_c3_sub')} state="run" />
      </div>
      {reached('bs_gate') && (
        <>
          <BsFan direction="join" />
          <BsGate text={tm('s1_bs_gate')} tone="amber" pulse />
          <BsNote tone="muted" text={tm('s1_bs_note')} />
        </>
      )}
    </Backstage>
  );
}

// ---------------------------------------------------------------- Act 2 —
// "She anticipates": two domains link themselves, initiative completes.

export function AnticipateChat({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <>
      {reached('user') && <UserBubble text={tm('s2_user')} />}
      {reached('weather') && (
        <AssistantRow bare footer={SCENARIO_FOOTERS.anticipate}>
          <WeatherCard
            title={tm('s2_card_title')}
            slots={[
              { icon: 'rain', label: tm('s2_slot1'), temp: '12°' },
              { icon: 'rain', label: tm('s2_slot2'), temp: '12°' },
              { icon: 'partly', label: tm('s2_slot3'), temp: '13°' },
            ]}
          />
        </AssistantRow>
      )}
      {reached('initiative') && (
        <AssistantRow variant="initiative">{tm('s2_initiative')}</AssistantRow>
      )}
      {reached('approve') && <UserBubble text={tm('s2_approve')} />}
      {reached('done') && (
        <AssistantRow variant="success">
          {tm('s2_done')}
          <AccentCard
            icon={<CalendarCheck className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />}
            title={tm('s2_event_title')}
            badges={[tm('s2_event_day'), tm('s2_event_time'), tm('s2_event_dur')]}
          />
        </AssistantRow>
      )}
    </>
  );
}

export function AnticipateBackstage({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <Backstage
      label={tm('backstage_label')}
      cost={BACKSTAGE_COSTS.anticipate}
      costLabel={tm('bs_cost_live')}
    >
      <BsQuery text={tm('s2_bs_query')} />
      <BsStem />
      <BsSparkLink
        left={
          <BsChip
            label={tm('s2_bs_c1')}
            sub={tm('s2_bs_c1_sub')}
            state={reached('bs_c1') ? 'done' : 'run'}
          />
        }
        right={<BsChip label={tm('s2_bs_c2')} sub={tm('s2_bs_c2_sub')} state="done" />}
        spark="✨"
        wiresDrawn={reached('bs_wire')}
        sparkShown={reached('bs_spark')}
      />
      {reached('bs_spark') && <BsNote tone="violet" text={tm('s2_bs_note')} />}
    </Backstage>
  );
}

// ---------------------------------------------------------------- Act 3 —
// "She reaches beyond the screen": agentic telephony (ADR-127).

export function CallChat({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <>
      {reached('user') && <UserBubble text={tm('s3_user')} />}
      {reached('hitl') && <AssistantRow variant="hitl">{tm('s3_hitl')}</AssistantRow>}
      {reached('approve') && <UserBubble text={tm('s3_approve')} />}
      {reached('done') && (
        <AssistantRow variant="success" footer={SCENARIO_FOOTERS.call}>
          {tm('s3_done')}
          <AccentCard
            icon={<Phone className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />}
            title={tm('s3_card_title')}
            badges={[tm('s3_card_day'), tm('s3_card_time'), tm('s3_card_pers')]}
          />
        </AssistantRow>
      )}
    </>
  );
}

export function CallBackstage({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <Backstage
      label={tm('backstage_label')}
      cost={BACKSTAGE_COSTS.call}
      costLabel={tm('bs_cost_live')}
    >
      <BsGate text={tm('s3_bs_gate')} tone="green" />
      {reached('bs_call') && (
        <>
          <BsStem />
          <BsCall name={tm('s3_bs_call')} sub={tm('s3_bs_call_sub')} />
          <BsNote tone="violet" text={tm('s3_bs_note')} />
        </>
      )}
    </Backstage>
  );
}

// ---------------------------------------------------------------- Act 4 —
// "She extends herself": a skill mini-app forged from a voice request.

export function CreateChat({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <>
      {reached('user') && <UserBubble text={tm('s4_user')} voice />}
      {reached('reply') && (
        <AssistantRow footer={SCENARIO_FOOTERS.create}>
          <span className="badge-glimmer inline-block rounded border border-cyan-500/30 bg-cyan-500/20 px-1.5 py-0.5 text-[9px] font-medium tracking-wide text-cyan-600 dark:text-cyan-400">
            ✦ {tm('s4_skill_badge')}
          </span>
          <span className="mt-1 block">{tm('s4_reply')}</span>
          <HydrationWidget
            title={tm('s4_widget_title')}
            filled={reached('fill') ? 6 : 5}
            total={8}
            addLabel={tm('s4_widget_btn1')}
            resetLabel={tm('s4_widget_btn2')}
            note={tm('s4_widget_note')}
            pressed={reached('fill')}
          />
        </AssistantRow>
      )}
    </>
  );
}

export function CreateBackstage({ reached }: ActProps) {
  const tm = useMockupT();
  return (
    <Backstage
      label={tm('backstage_label')}
      cost={BACKSTAGE_COSTS.create}
      costLabel={tm('bs_cost_live')}
    >
      <BsForge label={tm('s4_bs_forge')} sub={tm('s4_bs_forge_sub')} />
      <BsStem />
      <BsRail plugged={reached('bs_rail')} />
      {reached('bs_rail') && <BsNote tone="cyan" text={tm('s4_bs_note')} />}
    </Backstage>
  );
}
