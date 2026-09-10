/**
 * The two DEFERRED registers of ADR-263 (B8).
 *
 * `agent_effects` has its own section, read back from the database after the
 * fact. The other two arrive on the deferred channel, read from the LIVE
 * records: both recorders write when the turn closes, and the payload is
 * emitted inside them, so a database read at that instant would answer
 * « nothing » for a turn that consulted nine sources.
 *
 * Two things this section is careful about:
 *
 * - **the turn's outcome is « so far », not a verdict.** It starts at
 *   `interrupted` and only an explicit success moves it. The row is not written
 *   yet, so the section says « pending » rather than printing a conclusion the
 *   register has not reached.
 * - **a consultation names the CAPABILITY, never the call.** No argument
 *   crosses this boundary, by contract: « searched Marie's emails » would
 *   reveal a search nobody asked to have recorded.
 */

import React from 'react';
import { BookMarked } from 'lucide-react';

import { DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import { TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { RegistersMetrics } from '@/types/chat';

export interface RegistersSectionProps {
  data: RegistersMetrics | undefined;
}

/**
 * What each silent correction is called on screen (B8).
 *
 * A CLOSED vocabulary mirroring `core/turn_verdicts.py`: a kind nobody declared
 * would reach a reader as a raw identifier, so the fallback shows it verbatim
 * rather than inventing a sentence for it.
 */
const VERDICT_LABELS: Record<string, string> = {
  reasoning_coerced: 'Reasoning level coerced',
  parameter_clamped: 'Planner parameter clamped',
  history_repaired: 'History repaired',
  output_truncated: 'Truncated output refused',
  capability_refused: 'Capability refused',
  quota_refused: 'Quota refused',
};

/** How a turn's outcome reads while its row is still unwritten. */
const OUTCOME_TONE: Record<string, string> = {
  answered: TONE_TEXT.success,
  failed: TONE_TEXT.destructive,
  interrupted: TONE_TEXT.warning,
};

export const RegistersSection = React.memo(function RegistersSection({
  data,
}: RegistersSectionProps) {
  // Absent outside a turn: an empty block would say « this turn consulted
  // nothing and decided nothing » about a turn that is not there.
  if (!data) return null;

  const { decision, treatments } = data;
  const failed = treatments.failed_count;
  const verdicts = data.verdicts;

  return (
    <DebugSection
      value="registers"
      title="Registers"
      icon={BookMarked}
      anomaly={failed > 0}
      badge={
        <>
          <DebugChip tone="neutral">{treatments.count} read</DebugChip>
          {failed > 0 && <DebugChip tone="destructive">{failed} failed</DebugChip>}
          {verdicts != null && verdicts.count > 0 && (
            <DebugChip tone="warning">{verdicts.count} fixed</DebugChip>
          )}
        </>
      }
    >
      {decision && (
        <div className="space-y-1">
          <SubSectionHeader label="The turn" />
          <MetricRow label="Authority" value={decision.source} />
          <MetricRow label="Mode" value={decision.execution_mode} />
          {decision.route && <MetricRow label="Route" value={decision.route} />}
          {decision.plan_step_count != null && (
            <MetricRow label="Plan steps" value={decision.plan_step_count} />
          )}
          <MetricRow
            label="Outcome so far"
            value={decision.outcome}
            valueClassName={OUTCOME_TONE[decision.outcome] ?? undefined}
          />
          {decision.stop_reason && (
            <MetricRow label="Stopped because" value={decision.stop_reason} mono />
          )}
          {/* The row is written when the turn closes, which has not happened
              when this reaches the browser. Saying so is the difference
              between a reading and a verdict. */}
          {!decision.settled && (
            <p className="pt-0.5 text-[10px] italic text-muted-foreground">
              Read live — the register row is written when the turn closes.
            </p>
          )}
        </div>
      )}

      <div className="space-y-1">
        <SubSectionHeader label="Consulted" borderTop={Boolean(decision)} />
        {treatments.count === 0 ? (
          <p className="text-[10px] italic text-muted-foreground">
            This turn opened none of the person&apos;s sources.
          </p>
        ) : (
          <div className="space-y-0.5 text-[10px] text-muted-foreground">
            {treatments.entries.map((entry, index) => (
              <div
                key={`${entry.tool_name}-${index}`}
                className={cn(
                  'flex items-center justify-between gap-2',
                  entry.outcome !== 'ok' && TONE_TEXT.destructive
                )}
              >
                <span className="truncate font-mono" title={entry.tool_name}>
                  {entry.tool_name}
                </span>
                <span className="shrink-0 font-mono">
                  {entry.mutation_policy && (
                    <span className="mr-1.5 opacity-70">{entry.mutation_policy}</span>
                  )}
                  {entry.duration_ms}ms
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <SilentCorrections verdicts={verdicts} />
    </DebugSection>
  );
});

/**
 * What the turn quietly corrected about itself (B8).
 *
 * Six things routinely happen mid-turn and change what comes out — a coerced
 * reasoning level, a clamped parameter, a repaired history, a refused
 * truncation, a refused capability, a refused quota. Each is a REPAIR, not an
 * error, which is exactly why nobody ever saw them.
 *
 * @param props.verdicts - The block, absent on a payload from before B8.
 * @returns The rows, or null when the turn corrected nothing.
 */
function SilentCorrections({ verdicts }: { verdicts: RegistersMetrics['verdicts'] }) {
  if (!verdicts || verdicts.count === 0) return null;
  return (
    <div className="space-y-1">
      <SubSectionHeader label="Silently corrected" borderTop />
      <div className="space-y-0.5 text-[10px] text-muted-foreground">
        {verdicts.entries.map((entry, index) => (
          <div key={`${entry.kind}-${index}`} className="flex items-center justify-between gap-2">
            <span className={cn('font-mono', TONE_TEXT.warning)}>
              {VERDICT_LABELS[entry.kind] ?? entry.kind}
            </span>
            {entry.detail && (
              <span className="truncate font-mono opacity-70" title={entry.detail}>
                {entry.detail}
              </span>
            )}
          </div>
        ))}
      </div>
      {/* A capped list that does not say it is capped reads as an exact
          count (ADR-185). */}
      {verdicts.dropped > 0 && (
        <p className="text-[10px] italic text-muted-foreground">
          +{verdicts.dropped} more, past the per-turn cap.
        </p>
      )}
    </div>
  );
}
