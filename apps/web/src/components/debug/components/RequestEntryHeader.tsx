/**
 * RequestEntryHeader — the scannable header of one history entry.
 *
 * The COLLAPSED row already answers "what happened": route, engine,
 * duration, tokens, cost and anomaly count — so requests are compared by
 * scanning the history without unfolding anything.
 */

import React from 'react';
import { ChevronDown, Clock, MessageSquare, TriangleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DebugChip, NodeChip } from './shared';
import { formatClockTime, formatCost, formatDuration, formatTokenCount, truncateText } from '../utils/formatters';
import { QUERY_TRUNCATE_LENGTH } from '../utils/constants';
import type { DebugMetrics } from '@/types/chat';
import type { DebugMetricsEntry } from '@/types/chat-state';

export interface RequestEntryHeaderProps {
  entry: DebugMetricsEntry;
  isLatest: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  /** Anomaly count of this request (0 hides the counter). */
  anomalyCount: number;
}

/** Total run cost from every available spend family. */
function totalRunCostEur(metrics: DebugMetrics): number {
  return (
    (metrics.llm_summary?.total_cost_eur ?? 0) +
    (metrics.google_api_summary?.total_cost_eur ?? 0) +
    (metrics.image_generation_summary?.total_cost_eur ?? 0) +
    (metrics.voice?.total_cost_eur ?? 0)
  );
}

/** Anomaly counter shown next to the clock (nothing when the run is clean). */
function AnomalyCounter({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span
      title={`${count} anomal${count > 1 ? 'ies' : 'y'} on this request`}
      className="flex items-center gap-0.5 text-[10px] font-medium text-destructive"
    >
      <TriangleAlert className="h-3 w-3" aria-hidden="true" />
      {count}
    </span>
  );
}

/** Summary strip: compare requests without unfolding them. */
function EntrySummaryStrip({ metrics }: { metrics: DebugMetrics }) {
  const durationMs = metrics.request_lifecycle?.total_duration_ms ?? 0;
  const totalTokens = metrics.token_budget?.total_consumed;
  const cost = totalRunCostEur(metrics);

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
      {metrics.execution_mode === 'react' && <DebugChip tone="info">react</DebugChip>}
      {durationMs > 0 && <span className="font-mono">{formatDuration(durationMs)}</span>}
      {totalTokens !== undefined && (
        <span className="font-mono">{formatTokenCount(totalTokens)} tok</span>
      )}
      {cost > 0 && <span className="font-mono text-primary">{formatCost(cost)}</span>}
    </div>
  );
}

/** Collapsible, scannable header for one debug history entry. */
export const RequestEntryHeader = React.memo(function RequestEntryHeader({
  entry,
  isLatest,
  isExpanded,
  onToggle,
  anomalyCount,
}: RequestEntryHeaderProps) {
  const metrics = entry.metrics;
  const timestamp =
    entry.timestamp instanceof Date ? entry.timestamp : new Date(entry.timestamp);
  const route = metrics.routing_decision?.route_to;

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={isExpanded}
      className={cn(
        'flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-muted/50',
        isExpanded && 'bg-muted/30'
      )}
    >
      <ChevronDown
        aria-hidden="true"
        className={cn(
          'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
          !isExpanded && '-rotate-90'
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {isLatest && <DebugChip tone="info">LATEST</DebugChip>}
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" aria-hidden="true" />
            {formatClockTime(timestamp)}
          </span>
          <AnomalyCounter count={anomalyCount} />
        </div>
        <div className="mt-0.5 flex items-center gap-1">
          <MessageSquare className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate text-sm font-medium">
            {truncateText(entry.query, QUERY_TRUNCATE_LENGTH)}
          </span>
        </div>
        <EntrySummaryStrip metrics={metrics} />
      </div>
      {/* Route identity chip */}
      {route && <NodeChip nodeName={route === 'planner' ? 'planner' : 'chat'} />}
    </button>
  );
});
