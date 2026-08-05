/**
 * PipelineStrip — the pedagogical entry point of a request.
 *
 * One horizontal line of node chips with durations, in true chronological
 * order (the backend orders lifecycle nodes by first run-anchored
 * appearance): the flow is read BEFORE unfolding any section.
 */

import React from 'react';
import { ChevronRight } from 'lucide-react';
import { NodeChip } from './shared';
import { formatDuration } from '../utils/formatters';
import type { RequestLifecycleMetrics } from '@/types/chat';

export interface PipelineStripProps {
  /** Lifecycle nodes, chronologically ordered. */
  lifecycle: RequestLifecycleMetrics | undefined;
}

/** Horizontal phase strip of the request. */
export const PipelineStrip = React.memo(function PipelineStrip({ lifecycle }: PipelineStripProps) {
  if (!lifecycle || lifecycle.nodes.length === 0) return null;

  return (
    <div
      data-testid="pipeline-strip"
      className="flex flex-wrap items-center gap-1 border-b border-border/30 bg-muted/10 px-3 py-2"
    >
      {lifecycle.nodes.map((node, index) => (
        <React.Fragment key={node.name}>
          {index > 0 && (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
          )}
          <span className="flex items-center gap-1">
            <NodeChip nodeName={node.name} maxLength={18} />
            <span className="font-mono text-[9px] text-muted-foreground">
              {formatDuration(node.duration_ms || 0)}
            </span>
          </span>
        </React.Fragment>
      ))}
    </div>
  );
});
