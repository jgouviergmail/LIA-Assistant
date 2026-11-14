/**
 * TaskListBadge — the list a task is in, wherever tasks of several lists stand together: the
 * Tools' views across the lists and the home's tasks card (owner, 2026-11-10).
 *
 * A live trait with no semantic family: the theme colour, never grey. Its ground is SOLID, not
 * the theme's tint: on a row that is itself tinted (the open task's), tint over tint left the
 * name at 4.47:1 in dark, measured by axe on the production bundle (2026-11-10). The name is
 * the list's own, cut with an ellipsis where the row has no room, whole in its title; a screen
 * reader hears what the name is before the name. The component resolves no string: both
 * callers hand it their translated word for « list ».
 */
import { ListChecks } from '@/lib/icons';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export interface TaskListBadgeProps {
  /** The list's name. */
  name: string;
  /** The translated word for « list », read before the name by a screen reader. */
  label: string;
  className?: string;
}

export function TaskListBadge({ name, label, className }: TaskListBadgeProps) {
  return (
    <Badge
      variant="default"
      size="sm"
      title={name}
      className={cn('min-w-0 max-w-full bg-background', className)}
    >
      <ListChecks className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span className="sr-only">{label} </span>
      <span className="min-w-0 truncate">{name}</span>
    </Badge>
  );
}
