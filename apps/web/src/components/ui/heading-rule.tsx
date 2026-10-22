import { cn } from '@/lib/utils';

/**
 * The hairline that runs on from a rubrique's heading to the edge of its row.
 *
 * One shape for every page-level rubrique — the settings groups, the timeline
 * periods, the home sections, the relationship bands, the activity days — so a
 * logical separation looks the same on every screen (owner request
 * 2026-10-21). It draws the application's one neutral line colour; decorative,
 * so assistive technology skips it and reads the heading alone.
 *
 * Place it as a flex sibling of the heading: it takes whatever width is left.
 */
export function HeadingRule({ className }: { className?: string }) {
  return <span aria-hidden="true" className={cn('h-px min-w-3 flex-1 bg-border', className)} />;
}
