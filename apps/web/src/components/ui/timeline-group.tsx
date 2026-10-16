import type { ReactNode } from 'react';
import { CalendarDays, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TimelineGroupProps {
  headingId: string;
  heading: ReactNode;
  icon: LucideIcon;
  marker?: ReactNode;
  level: 2 | 3 | 4;
  /** Day and period hierarchy can appear below a page or a settings heading. */
  presentation?: 'day' | 'period';
  children: ReactNode;
  className?: string;
}

/** Named temporal section. Its caller supplies the grouping, order, dates and page boundary. */
export function TimelineGroup({
  headingId,
  heading,
  icon: Icon,
  marker,
  level,
  presentation = level === 2 ? 'day' : 'period',
  children,
  className,
}: TimelineGroupProps) {
  const Heading = level === 2 ? 'h2' : level === 3 ? 'h3' : 'h4';
  return (
    <section aria-labelledby={headingId} className={cn('min-w-0 space-y-3', className)}>
      <div className="flex min-w-0 items-center gap-3">
        {marker}
        <Heading
          id={headingId}
          className={cn(
            'flex min-w-0 items-center gap-2',
            presentation === 'day'
              ? 'text-base font-semibold'
              : 'text-xs font-medium text-muted-foreground'
          )}
        >
          <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          {heading}
        </Heading>
        {presentation === 'period' && (
          <span className="h-px min-w-3 flex-1 bg-border/60" aria-hidden="true" />
        )}
      </div>
      {children}
    </section>
  );
}

interface TimelineDayGroupProps extends Pick<
  TimelineGroupProps,
  'headingId' | 'heading' | 'level' | 'children'
> {
  dayNumber: string | null;
  month: string | null;
}

/** Shared civil-day marker and collection frame for meetings and recent calls. */
export function TimelineDayGroup({ dayNumber, month, children, ...props }: TimelineDayGroupProps) {
  return (
    <TimelineGroup
      {...props}
      icon={CalendarDays}
      presentation="day"
      marker={
        dayNumber &&
        month && (
          <span
            aria-hidden="true"
            className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl border border-primary/15 bg-primary/8 text-primary"
          >
            <span className="text-lg font-semibold leading-5">{dayNumber}</span>
            <span className="text-[10px] font-medium uppercase">{month}</span>
          </span>
        )
      }
    >
      <div className="overflow-hidden rounded-xl border border-border/70 bg-card shadow-sm">
        {children}
      </div>
    </TimelineGroup>
  );
}
