import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';

/** Loading state of the meetings pages (Next.js App Router `loading.tsx`). */
export default function Loading() {
  return (
    <div className="space-y-6">
      <LoadingAnnouncement />
      <div>
        <Skeleton className="mb-2 h-9 w-56" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    </div>
  );
}
