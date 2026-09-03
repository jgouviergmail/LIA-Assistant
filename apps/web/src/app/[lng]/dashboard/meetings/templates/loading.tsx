import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';

/** Loading state of the template library (Next.js App Router `loading.tsx`). */
export default function Loading() {
  return (
    <div className="space-y-6">
      <LoadingAnnouncement />
      <div>
        <Skeleton className="mb-2 h-9 w-64" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="space-y-3">
        {[1, 2, 3, 4].map(i => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  );
}
