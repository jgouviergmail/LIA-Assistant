import { Card } from '@/components/ui/card';
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton';

/**
 * Loading state for dashboard settings page
 * Follows Next.js 15 App Router loading.tsx pattern
 */
export default function Loading() {
  return (
    <div className="container mx-auto py-8 px-4 space-y-6">
      {/* Page Title Skeleton */}
      <div>
        <Skeleton className="h-10 w-64 mb-2" />
        <Skeleton className="h-4 w-96" />
      </div>

      {/* Connectors Section Skeleton */}
      <Card className="p-6">
        <Skeleton className="h-8 w-48 mb-4" />
        <div className="space-y-4">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      </Card>

      {/* Users Admin Section Skeleton */}
      <Card className="p-6">
        <Skeleton className="h-8 w-64 mb-4" />
        <Skeleton className="h-10 w-full mb-4" />
        <TableSkeleton rows={5} />
      </Card>

      {/* LLM Pricing Admin Section Skeleton */}
      <Card className="p-6">
        <Skeleton className="h-8 w-64 mb-4" />
        <Skeleton className="h-4 w-full mb-4" />
        <div className="flex gap-4 mb-4">
          <Skeleton className="h-10 flex-1" />
          <Skeleton className="h-10 w-40" />
        </div>
        <TableSkeleton rows={5} />
      </Card>
    </div>
  );
}
