import { cn } from '@/lib/utils';

/**
 * Loading placeholders.
 *
 * These are DECORATIVE by default: a skeleton is a picture of the layout that
 * is coming, and a screen reader gains nothing from hearing about each grey
 * rectangle. `TableSkeleton` used to nest one live region per cell — 24 of them
 * for a five-row table, inside another live region.
 *
 * When a section does need to announce that it is loading, the caller passes
 * `label` (already resolved from the active locale) and gets exactly ONE live
 * region. The primitive never invents that string itself: these components are
 * rendered by App Router SERVER components (`dashboard/settings/loading.tsx`,
 * `dashboard/spaces/loading.tsx`), where a client i18n hook cannot run — which
 * is why the previous hardcoded "Loading..." could not simply be translated.
 */

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
  /**
   * Localised screen-reader label. Omit it — the default — for a decorative
   * placeholder; pass it to make this block the section's single loading
   * announcement.
   */
  label?: string;
}

/** Props of the composed skeletons, which only expose the label. */
interface LabelledSkeletonProps {
  /** Localised screen-reader label; omit for a decorative placeholder. */
  label?: string;
}

/**
 * Announce-or-hide attributes for a skeleton container.
 *
 * Args:
 *   label: The localised label, when the block should announce itself.
 *
 * Returns:
 *   Either a single live region, or a subtree hidden from assistive tech.
 */
function announcement(label?: string) {
  return label
    ? ({ role: 'status', 'aria-label': label } as const)
    : ({ 'aria-hidden': true } as const);
}

export function Skeleton({ className, label, ...props }: SkeletonProps) {
  return (
    <div
      {...announcement(label)}
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  );
}

/**
 * Table skeleton for loading table data.
 *
 * Args:
 *   rows: How many body rows to draw.
 *   label: Localised announcement; omit to stay decorative.
 */
export function TableSkeleton({ rows = 5, label }: { rows?: number } & LabelledSkeletonProps) {
  return (
    <div className="space-y-3" {...announcement(label)}>
      {/* Table header skeleton */}
      <div className="flex gap-4 border-b pb-3">
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/4" />
      </div>

      {/* Table rows skeleton */}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 py-3">
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 w-1/4" />
        </div>
      ))}
    </div>
  );
}

/**
 * Card skeleton for loading card-based layouts.
 *
 * Args:
 *   label: Localised announcement; omit to stay decorative.
 */
export function CardSkeleton({ label }: LabelledSkeletonProps) {
  return (
    // `bg-card`, not `bg-white`: the previous literal painted a white card on
    // the dark theme's near-black page.
    <div className="rounded-lg border bg-card p-6 shadow-sm" {...announcement(label)}>
      <Skeleton className="mb-4 h-6 w-3/4" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="mb-2 h-4 w-5/6" />
      <Skeleton className="h-4 w-4/6" />
    </div>
  );
}
