/**
 * ActionBadge — create/update/delete action chip.
 *
 * Used across Memory, Journal, and Interest extraction sections for
 * consistent action display. Unknown actions render as-is on a neutral
 * chip — never a silent fallback to CREATE, which claimed an action
 * nobody took.
 */

import React from 'react';
import { DebugChip } from './DebugChip';
import type { DebugTone } from '../../utils/tones';

export type ActionType = 'create' | 'update' | 'delete' | 'consolidate' | 'create_new';

const ACTION_STYLE: Record<ActionType, { tone: DebugTone; label: string }> = {
  create: { tone: 'success', label: 'CREATE' },
  create_new: { tone: 'success', label: 'CREATE' },
  update: { tone: 'warning', label: 'UPDATE' },
  consolidate: { tone: 'info', label: 'MERGE' },
  delete: { tone: 'destructive', label: 'DELETE' },
};

export interface ActionBadgeProps {
  action: string;
  className?: string;
}

/** Action chip with semantic tone; unknown actions stay neutral. */
export const ActionBadge = React.memo(function ActionBadge({
  action,
  className,
}: ActionBadgeProps) {
  const style = ACTION_STYLE[action as ActionType] ?? {
    tone: 'neutral' as const,
    label: action.toUpperCase(),
  };

  return (
    <DebugChip tone={style.tone} className={className}>
      {style.label}
    </DebugChip>
  );
});
