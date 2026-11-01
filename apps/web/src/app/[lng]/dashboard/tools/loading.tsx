import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';

/** A tool page loading inside the section's frame (Next.js App Router `loading.tsx`). */
export default function Loading() {
  return (
    <div className="space-y-4">
      <LoadingAnnouncement />
      <Skeleton className="h-8 w-48" />
      <div className="space-y-3">
        {[1, 2, 3, 4].map(i => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  );
}
