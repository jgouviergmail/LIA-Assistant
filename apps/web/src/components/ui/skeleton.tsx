import { cn } from '@/lib/utils';

/**
 * Skeleton component for loading states
 * Provides accessible loading placeholders with proper ARIA attributes
 */
interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading..."
      className={cn('animate-pulse rounded-md bg-gray-200 dark:bg-gray-700', className)}
      {...props}
    >
      <span className="sr-only">Loading...</span>
    </div>
  );
}

/**
 * Table skeleton for loading table data
 */
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading table data">
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

      <span className="sr-only">Loading table data...</span>
    </div>
  );
}

/**
 * Card skeleton for loading card-based layouts
 */
export function CardSkeleton() {
  return (
    <div
      className="rounded-lg border bg-white p-6 shadow-sm"
      role="status"
      aria-label="Loading card"
    >
      <Skeleton className="mb-4 h-6 w-3/4" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="mb-2 h-4 w-5/6" />
      <Skeleton className="h-4 w-4/6" />
      <span className="sr-only">Loading card...</span>
    </div>
  );
}
