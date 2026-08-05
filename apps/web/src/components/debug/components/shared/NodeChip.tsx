/**
 * NodeChip — identity chip for a LangGraph node name.
 *
 * Node identities are not statuses: each family keeps a distinct, stable
 * hue, always as a bi-theme pair (see `nodeChipClasses`). The name renders
 * in mono because it is a technical identifier.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { nodeChipClasses } from '../../utils/tones';
import { truncateText } from '../../utils/formatters';

export interface NodeChipProps {
  /** LangGraph node name (router, planner, react_call_model…). */
  nodeName: string;
  /** Truncate the displayed name beyond this length (full name in tooltip). */
  maxLength?: number;
  /** Additional CSS classes. */
  className?: string;
}

/** Identity chip for a pipeline node. */
export const NodeChip = React.memo(function NodeChip({
  nodeName,
  maxLength = 24,
  className,
}: NodeChipProps) {
  const truncated = truncateText(nodeName, maxLength);
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-1.5 py-0.5 font-mono text-[10px] whitespace-nowrap',
        nodeChipClasses(nodeName),
        className
      )}
      title={truncated === nodeName ? undefined : nodeName}
    >
      {truncated}
    </span>
  );
});
