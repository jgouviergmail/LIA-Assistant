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

/** One sandboxed script (ADR-249) — admin surface only. */
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

export const ReactExecutionSection = React.memo(function ReactExecutionSection({
  data,
}: ReactExecutionSectionProps) {
  // Absent entirely in pipeline mode: the orchestrator only mounts this
  // section when the turn ran in ReAct mode.
  if (!data) return null;

  const atCeiling = data.max_iterations > 0 && data.iterations >= data.max_iterations;

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
          {data.iterations}/{data.max_iterations}
        </DebugChip>
      }
    >
      {/* Loop metrics */}
      <div className="space-y-1">
        <SubSectionHeader label="Loop" />
        <MetricRow
          label="Iterations"
          value={`${data.iterations}/${data.max_iterations}`}
          highlight
        />
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
        max={data.max_iterations}
        label="Iteration budget"
        exhaustedLabel="The loop hit its iteration ceiling — the answer may be a forced finalization."
      />

      {hasToolTime && (
        <BudgetBar
          value={toolSeconds}
          max={toolBudget}
          label="Tool-time budget"
          exhaustedLabel="The loop spent its tool budget — delegated work was cut short."
        />
      )}

      {/* Sandboxed scripts (ADR-249) — admin surface only: the code the model
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
