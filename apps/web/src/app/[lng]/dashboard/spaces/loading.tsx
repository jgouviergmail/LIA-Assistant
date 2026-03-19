import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading state for RAG Spaces page.
 * Follows Next.js App Router loading.tsx pattern.
 */
export default function Loading() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Skeleton className="h-9 w-56 mb-2" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-10 w-36" />
      </div>

      {/* Cards grid skeleton */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-40 rounded-lg border bg-muted/50 animate-pulse" />
        ))}
      </div>
    </div>
  );
}
