'use client';

/**
 * Guided interactive mission: one synthetic storyboard of the /demo showroom.
 *
 * A deterministic, client-only storyboard driven by the pure mission reducer
 * over an immutable mission definition. Reuses the REAL HitlActionCard and
 * ExecutionTraceDisclosure contracts against synthetic state — no agent,
 * provider, connector, or API call ever happens here — and closes on LIA's
 * reply rendered by the PRODUCTION rich-HTML pipeline. Honesty labels stay
 * visible throughout; timer pacing is a demonstration sequence and is
 * replaced by explicit Continue buttons under prefers-reduced-motion.
 *
 * Decomposed by phase (sources / planning / decisions / receipt) so every
 * function stays well under the complexity cap and reads as the storyboard.
 */

import { useEffect, useMemo, useRef } from 'react';
import { BellRing, LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { HitlActionCard } from '@/components/chat/HitlActionCard';
import { ExecutionTraceDisclosure } from '@/components/chat/ExecutionTraceDisclosure';
import { ExecutionReceipt } from '@/components/showroom/ExecutionReceipt';
import { HonestyStrip } from '@/components/showroom/HonestyStrip';
import { MissionDemoNote } from '@/components/showroom/MissionDemoNote';
import { MissionActions } from '@/components/showroom/MissionActions';
import { ShowroomRichResponse } from '@/components/showroom/ShowroomRichResponse';
import { buildShowroomResponseHtml } from '@/components/showroom/response-html';
import {
  buildDecisionCard,
  buildShowroomTrace,
  resolveCard,
} from '@/components/showroom/hitl-adapter';
import { getConfiguredProofSha, getShowroomProofLinks } from '@/components/showroom/proof-links';
import {
  missionTraceDurationMs,
  useShowroomMission,
  type ShowroomFunnelEvent,
  type ShowroomMissionHandle,
} from '@/components/showroom/useShowroomMission';
import type {
  ShowroomDecisionKind,
  ShowroomMissionDefinition,
  ShowroomState,
} from '@/components/showroom/types';
import type { ExecutionTrace } from '@/types/execution-trace';
import type { HitlCardState } from '@/types/hitl';
import { Button } from '@/components/ui/button';
import { useFollowLatest } from '@/hooks/useFollowLatest';
import { useMediaQuery } from '@/hooks/useMediaQuery';

export interface ShowroomMissionProps {
  def: ShowroomMissionDefinition;
  /** Bounded funnel sink; the page wires the credential-less emitter. */
  onEvent?: (event: ShowroomFunnelEvent) => void;
  /** Back to the mission picker (header + receipt utility row). */
  onChangeMission: () => void;
}

/** The visitor request — or, on proactive missions, LIA's own trigger. */
function MissionRequest({ t, def }: { t: TFunction; def: ShowroomMissionDefinition }) {
  if (!def.proactive) {
    return (
      <blockquote data-testid="showroom-request" className="rounded-xl border border-border/60 bg-card/70 p-4 text-sm italic leading-relaxed text-foreground backdrop-blur-sm">
        {t(def.requestKey)}
      </blockquote>
    );
  }
  return (
    <div data-testid="showroom-request" className="rounded-xl border border-primary/30 bg-card/70 p-4 leading-relaxed backdrop-blur-sm">
      {/* A title, so its icon takes the theme colour (apps/web CLAUDE.md). */}
      <p className="flex items-center gap-2 text-xs font-semibold text-primary">
        <BellRing className="h-4 w-4 shrink-0" aria-hidden="true" />
        {t('showroom.proactive_intro')}
      </p>
      <p className="mt-2.5 text-sm text-foreground">{t(def.requestKey)}</p>
    </div>
  );
}

/** The synthetic sources, revealed progressively during reading. */
function MissionSources({
  t,
  def,
  state,
}: {
  t: TFunction;
  def: ShowroomMissionDefinition;
  state: ShowroomState;
}) {
  const visible = state.phase === 'reading_sources' ? state.sourcesRead : def.sources.length;
  return (
    <ol aria-label={t('showroom.sources.title')} className="grid gap-2 sm:grid-cols-2">
      {def.sources.slice(0, visible).map(source => (
        <li
          key={source.id}
          className="rounded-xl border border-border/60 bg-card/70 p-3 backdrop-blur-sm"
        >
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            <span aria-hidden="true">{source.emoji}</span>
            {t(source.labelKey)}
          </p>
          <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {source.items.map(item => (
              <p key={item.labelKey}>
                {t(item.labelKey)}
                {item.time && (
                  <>
                    {' '}
                    <span className="font-medium text-foreground">
                      {item.time}
                      {item.endTime ? `–${item.endTime}` : ''}
                    </span>
                  </>
                )}
              </p>
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Planning findings plus the reasoning-free storyboard trace. */
function MissionPlanning({
  t,
  def,
  trace,
}: {
  t: TFunction;
  def: ShowroomMissionDefinition;
  trace: ExecutionTrace;
}) {
  return (
    <div className="space-y-2">
      <ul className="space-y-1 text-xs text-muted-foreground">
        {def.findings.map(finding => (
          <li key={finding.labelKey}>
            ⚠️ {t(finding.labelKey)}
            {finding.time && (
              <>
                {' '}
                <span className="font-medium text-foreground">
                  {finding.time}
                  {finding.endTime ? `–${finding.endTime}` : ''}
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center">
        <ExecutionTraceDisclosure trace={trace} />
      </div>
    </div>
  );
}

/** The mission's HITL decision cards over synthetic state, in order. */
function MissionDecisions({
  state,
  cards,
  mission,
}: {
  state: ShowroomState;
  cards: readonly HitlCardState[];
  mission: ShowroomMissionHandle;
}) {
  const reached = (index: number): boolean =>
    state.phase === 'receipt' || (state.phase === 'decision' && state.decisionIndex >= index);
  return (
    <>
      {cards.map((card, index) => {
        if (!reached(index)) return null;
        const decided = state.decisions[index];
        return (
          <div
            // Adapter cards always carry a payload; the fallback only guards
            // the nullable type of the shared chat contract.
            key={card.payload?.messageId ?? `decision-${index}`}
            data-testid={`showroom-decision-${index}`}
          >
            <HitlActionCard
              hitl={decided === null ? card : resolveCard(card, decided)}
              onAction={wireAction => {
                mission.decide(index, wireAction as ShowroomDecisionKind);
              }}
            />
          </div>
        );
      })}
    </>
  );
}

/** Rich reply, demo note, receipt and the redesigned action rows. */
function MissionReceipt({
  t,
  def,
  state,
  mission,
  onChangeMission,
}: {
  t: TFunction;
  def: ShowroomMissionDefinition;
  state: ShowroomState;
  mission: ShowroomMissionHandle;
  onChangeMission: () => void;
}) {
  const proofLinks = useMemo(() => getShowroomProofLinks(getConfiguredProofSha()), []);
  const responseHtml = useMemo(
    () => buildShowroomResponseHtml(def.id, t, state.decisions),
    [def.id, t, state.decisions]
  );
  return (
    <div className="space-y-3" data-testid="showroom-receipt">
      <ShowroomRichResponse html={responseHtml} />
      <MissionDemoNote noteKey={def.noteKey} />
      <ExecutionReceipt def={def} decisions={state.decisions} />
      <MissionActions
        proofLinks={proofLinks}
        onRestart={mission.restart}
        onChangeMission={onChangeMission}
        onProofOpened={mission.markProofOpened}
        onCta={mission.markCta}
      />
    </div>
  );
}

function phaseLabelKey(def: ShowroomMissionDefinition, state: ShowroomState): string {
  if (state.phase === 'decision') {
    return def.decisions[state.decisionIndex]?.phaseLabelKey ?? 'showroom.phases.receipt';
  }
  return `showroom.phases.${state.phase}`;
}

export function ShowroomMission({ def, onEvent, onChangeMission }: ShowroomMissionProps) {
  const { t } = useTranslation();
  const stillness = useMediaQuery('(prefers-reduced-motion: reduce)');
  const mission = useShowroomMission({ def, paced: !stillness, onEvent });
  const { state } = mission;
  const phaseHeadingRef = useRef<HTMLHeadingElement>(null);

  // Focus intent: each new phase moves focus to its heading (skip 'ready',
  // where the Start button is the natural target).
  //
  // `preventScroll`: focusing also scrolls, and it scrolls the HEADING to the
  // top — the opposite of following the content appended below it. Two scrolls
  // fighting per phase also read as a jump. The sentinel below is the single
  // authority on where the viewport goes.
  useEffect(() => {
    if (state.phase !== 'ready') phaseHeadingRef.current?.focus({ preventScroll: true });
  }, [state.phase, state.decisionIndex]);

  // What counts as "new content appeared": a phase change, one more source
  // revealed, one more decision reached, or a decision answered.
  const followMarker = `${state.phase}:${state.sourcesRead}:${state.decisionIndex}:${
    state.decisions.filter(decision => decision !== null).length
  }`;
  const followRef = useFollowLatest(followMarker, {
    active: state.phase !== 'ready',
    smooth: !stillness,
  });

  const cards = useMemo(
    () => def.decisions.map(spec => buildDecisionCard(state.runId, def.id, spec, t)),
    [def, state.runId, t]
  );
  const trace = useMemo(
    () =>
      buildShowroomTrace(
        def.traceKeys.map(key => t(key)),
        missionTraceDurationMs(def)
      ),
    [def, t]
  );

  const started = state.phase !== 'ready';
  const planned = started && state.phase !== 'reading_sources';
  const showContinue =
    stillness && (state.phase === 'reading_sources' || state.phase === 'planning');

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <header className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* `text-xl`: the mission title outranks the phase headings below
              it (`text-sm`), which it used to sit almost level with. */}
          <h2 className="text-xl font-semibold text-foreground">{t(def.titleKey)}</h2>
          {/* Always reachable: a visitor may leave a mission mid-run. */}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid="showroom-back-to-picker"
            onClick={onChangeMission}
          >
            <LayoutGrid className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            {t('showroom.change_mission')}
          </Button>
        </div>
        <HonestyStrip />
        <MissionRequest t={t} def={def} />
      </header>

      {/* Single polite region announcing the current phase. */}
      <p role="status" aria-live="polite" className="sr-only">
        {t(phaseLabelKey(def, state))}
      </p>

      {!started && (
        <Button type="button" data-testid="showroom-start" onClick={mission.start}>
          {t('showroom.start')}
        </Button>
      )}

      {started && (
        <h3
          ref={phaseHeadingRef}
          tabIndex={-1}
          className="text-sm font-medium text-foreground outline-none"
        >
          {t(phaseLabelKey(def, state))}
        </h3>
      )}

      {started && <MissionSources t={t} def={def} state={state} />}
      {planned && <MissionPlanning t={t} def={def} trace={trace} />}

      {showContinue && (
        <Button
          type="button"
          variant="outline"
          data-testid="showroom-continue"
          onClick={mission.advance}
        >
          {t('showroom.continue')}
        </Button>
      )}

      <MissionDecisions state={state} cards={cards} mission={mission} />

      {state.phase === 'receipt' && (
        <MissionReceipt
          t={t}
          def={def}
          state={state}
          mission={mission}
          onChangeMission={onChangeMission}
        />
      )}

      {/* Scroll anchor. `scroll-mb-24` is the requested room below the latest
          element: `scrollIntoView` honours scroll-margin, so the viewport
          stops short of the very bottom without a spacer that would show as
          empty space at rest. Decorative — it carries no content. */}
      <div
        ref={followRef}
        data-testid="showroom-follow-sentinel"
        aria-hidden="true"
        className="h-px scroll-mb-24"
      />
    </div>
  );
}
