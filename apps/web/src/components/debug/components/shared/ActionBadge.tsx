/**
 * ActionBadge - Displays create/update/delete action with color coding.
 *
 * Used across Memory, Journal, and Interest extraction sections
 * for consistent action display.
 */

import React from 'react';
import { cn } from '@/lib/utils';

export type ActionType = 'create' | 'update' | 'delete' | 'consolidate' | 'create_new';

const ACTION_STYLES: Record<
  ActionType,
  { bg: string; text: string; border: string; label: string }
> = {
  create: {
    bg: 'bg-emerald-500/20',
    text: 'text-emerald-400',
    border: 'border-emerald-400/30',
    label: 'CREATE',
  },
  create_new: {
    bg: 'bg-emerald-500/20',
    text: 'text-emerald-400',
    border: 'border-emerald-400/30',
    label: 'CREATE',
  },
  update: {
    bg: 'bg-amber-500/20',
    text: 'text-amber-400',
    border: 'border-amber-400/30',
    label: 'UPDATE',
  },
  consolidate: {
    bg: 'bg-blue-500/20',
    text: 'text-blue-400',
    border: 'border-blue-400/30',
    label: 'MERGE',
  },
  delete: {
    bg: 'bg-red-500/20',
    text: 'text-red-400',
    border: 'border-red-400/30',
    label: 'DELETE',
  },
};

export interface ActionBadgeProps {
  action: string;
  className?: string;
}

export const ActionBadge = React.memo(function ActionBadge({
  action,
  className,
}: ActionBadgeProps) {
  const style = ACTION_STYLES[action as ActionType] ?? ACTION_STYLES.create;

  return (
    <span
      className={cn(
        'text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 uppercase tracking-wider',
        style.bg,
        style.text,
        style.border,
        className
      )}
    >
      {style.label}
    </span>
  );
});
