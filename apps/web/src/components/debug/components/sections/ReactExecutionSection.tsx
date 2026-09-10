/**
 * ReAct Execution Section Component (v3.4, ADR-070)
 *
 * The autonomous loop of the turn: iterations against the PUBLISHED bound
 * (ADR-184: an enforced limit travels with the value it constrains), the two
 * time budgets, and the tool roster the loop could draw from.
 *
 * ADR-256: a turn spends time in two places and only one of them used to be
 * shown. "Elapsed" counted the model's reasoning alone, so a delegated
 * sub-agent loop — 20 nested LLM iterations behind a single tool call — read
 * as zero here. Reasoning and tool time are now separate rows with separate
 * bounds, drawn by one shared `BudgetBar`.
 */

import React from 'react';
import { Repeat2 } from 'lucide-react';
import { BudgetBar, DebugChip, DebugSection, MetricRow, SubSectionHeader } from '../shared';
import { TONE_TEXT } from '../../utils/tones';
import { cn } from '@/lib/utils';
import type { EphemeralScript, ReactExecutionMetrics } from '@/types/chat';

export interface ReactExecutionSectionProps {
  data: ReactExecutionMetrics | undefined;
}

/** One sandboxed script (ADR-249) — the debug panel, never the answer. */
const ScriptCard = React.memo(function ScriptCard({ script }: { script: EphemeralScript }) {
  return (
    <div className="rounded border border-border p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[11px] font-medium">{script.purpose}</span>
        <DebugChip tone={script.success ? 'info' : 'warning'}>
          {script.success ? 'ok' : 'failed'}
        </DebugChip>
      </div>
      <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-1.5 font-mono text-[10px]">
        {script.code}
      </pre>
      {script.output_head ? (
        <pre
          className={cn(
            'mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-words rounded p-1.5 font-mono text-[10px]',
            script.success ? 'bg-muted/50' : TONE_TEXT.warning
          )}
        >
          {script.output_head}
        </pre>
      ) : null}
    </div>
  );
});

/**
 * The capabilities the turn asked for and never got (B8).
 *
 * The signal that says whether the budget is CALIBRATED, not merely that it was
 * hit. These calls were answered with an explicit « never ran » so the history
 * stays valid by construction (ADR-248, invariant 4); before B8 they reached a
 * log line and nothing a person could read.
 *
 * @param props.names - The tool names.
 * @returns The block, or null when the loop abandoned nothing.
 */
function AbandonedCalls({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div className="space-y-1">
      <SubSectionHeader label="Asked for, never ran" borderTop />
      <div className="flex flex-wrap gap-1">
        {names.map((name, index) => (
          <DebugChip key={`${name}-${index}`} tone="warning">
            {name}
          </DebugChip>
        ))}
      </div>
    </div>
  );
}

/**
 * What governed this loop, derived once (B8).
 *
 * The bound the loop ACTUALLY stops at is ADR-238's domain-span allowance,
 * extended while the loop keeps producing (ADR-248). Drawing the ceiling
 * instead made a turn narrowed to four iterations read as « 4/25 » — a model
 * that gave up, when in fact it spent exactly the budget it was given. A
 * payload persisted before B8 carries neither, so both fall back to the
 * ceiling it did publish.
 *
 * @param data - The ReAct metrics.
 * @returns The budget, the ceiling, whether the budget was spent, whether the
 *   turn was narrowed, and the calls it never got to run.
 */
function loopBounds(data: ReactExecutionMetrics): {
  budget: number;
  ceiling: number;
  atCeiling: boolean;
  narrowed: boolean;
  abandoned: string[];
} {
  const budget = data.iteration_budget ?? data.max_iterations;
  const ceiling = data.iteration_ceiling ?? data.max_iterations;
  return {
    budget,
    ceiling,
    atCeiling: budget > 0 && data.iterations >= budget,
    narrowed: budget > 0 && ceiling > budget,
    abandoned: data.abandoned_calls ?? [],
  };
}

/**
 * What governed the loop, beside the iteration count (B8).
 *
 * Its own component so the section stays under the complexity cap: three rows
 * that each exist only under a condition are three branches, and the section
 * already carries the scripts, the budgets and the tool list.
 *
 * @param props.data - The ReAct metrics.
 * @param props.budget - The bound the loop actually stops at.
 * @param props.ceiling - The hard cap.
 * @param props.narrowed - Whether ADR-238 gave this turn less than the cap.
 * @returns The rows.
 */
function LoopBounds({
  data,
  budget,
  ceiling,
  narrowed,
}: {
  data: ReactExecutionMetrics;
  budget: number;
  ceiling: number;
  narrowed: boolean;
}) {
  const earned =
    typeof data.starting_budget === 'number' && budget > data.starting_budget
      ? budget - data.starting_budget
      : 0;
  return (
    <>
      {/* The ceiling is a DIFFERENT number from the budget whenever ADR-238
          narrowed the turn: showing only one of the two answers half the
          question « did it have room? ». */}
      {narrowed && (
        <MetricRow label="Ceiling" value={ceiling} valueClassName="text-muted-foreground" />
      )}
      {earned > 0 && (
        <MetricRow
          label="Earned"
          value={`+${earned} (from ${data.productive_iterations ?? 0} productive)`}
        />
      )}
      {data.exit_reason && (
        <MetricRow
          label="Stopped because"
          value={data.exit_reason}
          mono
          valueClassName={data.exit_reason === 'answered' ? TONE_TEXT.success : TONE_TEXT.warning}
        />
      )}
    </>
  );
}

export const ReactExecutionSection = React.memo(function ReactExecutionSection({
  data,
}: ReactExecutionSectionProps) {
  // Absent entirely in pipeline mode: the orchestrator only mounts this
  // section when the turn ran in ReAct mode.
  if (!data) return null;

  const { budget, ceiling, atCeiling, narrowed, abandoned } = loopBounds(data);

  // Absent on payloads persisted before ADR-256: that turn has no tool row at
  // all, rather than a zero it never measured.
  const toolSeconds = data.tool_seconds;
  const toolBudget = data.tool_budget_seconds ?? 0;
  const hasToolTime = typeof toolSeconds === 'number';
  const atToolBudget = hasToolTime && toolBudget > 0 && toolSeconds >= toolBudget;

  const scripts = data.scripts ?? [];

  return (
    <DebugSection
      value="react_execution"
      title="ReAct Loop"
      icon={Repeat2}
      anomaly={atCeiling || atToolBudget}
      badge={
        <DebugChip tone={atCeiling || atToolBudget ? 'warning' : 'info'}>
          {data.iterations}/{budget}
        </DebugChip>
      }
    >
      {/* Loop metrics */}
      <div className="space-y-1">
        <SubSectionHeader label="Loop" />
        <MetricRow label="Iterations" value={`${data.iterations}/${budget}`} highlight />
        <LoopBounds data={data} budget={budget} ceiling={ceiling} narrowed={narrowed} />
        <MetricRow label="Reasoning" value={`${data.elapsed_seconds.toFixed(1)}s`} mono />
        {hasToolTime && (
          <MetricRow
            label="Tools"
            value={
              toolBudget > 0
                ? `${toolSeconds.toFixed(1)}s / ${toolBudget}s`
                : `${toolSeconds.toFixed(1)}s`
            }
            mono
          />
        )}
        <MetricRow label="Tool calls executed" value={data.executed_tool_calls} />
      </div>

      <BudgetBar
        value={data.iterations}
        max={budget}
        label="Iteration budget"
        exhaustedLabel="The loop spent its iteration budget — the answer may be a forced finalization."
      />

      <AbandonedCalls names={abandoned} />

      {hasToolTime && (
        <BudgetBar
          value={toolSeconds}
          max={toolBudget}
          label="Tool-time budget"
          exhaustedLabel="The loop spent its tool budget — delegated work was cut short."
        />
      )}

      {/* Sandboxed scripts (ADR-249) — the debug panel and nowhere else: the code the model
          wrote is shown here and nowhere else, because a computation nobody
          can read is exactly what the script was meant to replace. */}
      {scripts.length > 0 && (
        <div>
          <SubSectionHeader label={`Sandboxed scripts (${scripts.length})`} borderTop />
          <div className="space-y-2">
            {scripts.map((script, index) => (
              <ScriptCard key={`${script.purpose}-${index}`} script={script} />
            ))}
          </div>
        </div>
      )}

      {/* Tool roster */}
      {data.tool_names.length > 0 && (
        <div>
          <SubSectionHeader label={`Available tools (${data.tool_names.length})`} borderTop />
          <div className="flex flex-wrap gap-1">
            {data.tool_names.map(name => (
              <span
                key={name}
                className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </DebugSection>
  );
});
