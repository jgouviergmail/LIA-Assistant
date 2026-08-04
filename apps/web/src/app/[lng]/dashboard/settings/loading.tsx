import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading state for the dashboard settings page.
 *
 * A skeleton is a promise about what is coming, so it only draws what EVERY
 * user actually gets. The previous version sketched "Connectors", "Users Admin"
 * and "LLM Pricing" — two of them superuser-only sections a standard account
 * never sees — and wrapped them in `container mx-auto py-8 px-4`, a second set
 * of gutters on top of the dashboard `<main>`, so the content jumped sideways
 * and upwards the moment the real page replaced it.
 *
 * The shape below mirrors `settings/page.tsx`: the same `space-y-6` rhythm, a
 * title, a subtitle, the tab bar, then neutral collapsed sections.
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

      {/* Tab bar */}
      <div className="flex gap-2">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-32" />
      </div>

      {/* Collapsed settings sections — present for every account, whatever its role */}
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-16 w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}
