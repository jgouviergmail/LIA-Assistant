import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading state for the dashboard settings page.
 *
 * A skeleton is a promise about what is coming, so it draws the master-detail
 * geometry every user actually gets: header, then the rail (search field +
 * grouped entries) beside the overview cards. Below `lg` the rail is the whole
 * landing screen, exactly like the real page. No superuser-only shapes.
 */
export default function Loading() {
  return (
    <div className="space-y-6">
      <LoadingAnnouncement />

      {/* Header — the h1 + subtitle of the real page */}
      <div>
        <Skeleton className="h-9 w-56" />
        <Skeleton className="mt-2 h-5 w-80" />
      </div>

      <div className="lg:flex lg:items-start lg:gap-8">
        {/* Rail: search field, then grouped entries */}
        <div className="space-y-4 lg:w-64 lg:shrink-0">
          <Skeleton className="h-9 w-full rounded-lg" />
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-full rounded-md" />
            ))}
          </div>
        </div>

        {/* Overview cards — hidden below lg, like the real pane */}
        <div className="hidden min-w-0 flex-1 lg:block">
          <Skeleton className="mb-3 h-5 w-44" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
