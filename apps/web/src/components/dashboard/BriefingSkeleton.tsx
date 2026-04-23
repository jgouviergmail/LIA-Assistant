'use client';

/**
 * Granular skeletons used while briefing data is loading.
 *
 * They mirror the final layout shape so the visual transition is seamless.
 * Each can be used independently — the page renders progressively as the
 * non-blocking queries (cards + synthesis) resolve at their own pace.
 */

export function GreetingSkeleton() {
  return (
    <div className="py-6 sm:py-8 text-center" aria-hidden="true">
      <div className="mx-auto h-6 sm:h-7 w-2/3 max-w-md rounded-md bg-muted/60 animate-pulse" />
      <div className="mx-auto mt-3 h-px w-20 bg-muted/30" />
    </div>
  );
}

export function SynthesisSkeleton() {
  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-primary/10 bg-gradient-to-br from-primary/5 via-card/80 to-card backdrop-blur-md p-5 sm:p-6 space-y-2"
      aria-hidden="true"
    >
      <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary/20" />
      <div className="h-4 w-full rounded bg-muted/60 animate-pulse" />
      <div className="h-4 w-5/6 rounded bg-muted/60 animate-pulse" />
      <div className="h-4 w-2/3 rounded bg-muted/60 animate-pulse" />
    </div>
  );
}

export function CardsGridSkeleton() {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5"
      aria-hidden="true"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="relative overflow-hidden rounded-2xl border border-border/50 bg-card p-5 sm:p-6 space-y-4 h-[280px]"
        >
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-muted/60 animate-pulse" />
            <div className="h-3 w-1/3 rounded bg-muted/60 animate-pulse" />
          </div>
          <div className="space-y-2">
            <div className="h-7 w-1/2 rounded bg-muted/70 animate-pulse" />
            <div className="h-4 w-3/4 rounded bg-muted/50 animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Backward-compatible full-page skeleton (used when an unknown error happens
 * to avoid white-screen). Kept as a safety net.
 */
export function BriefingSkeleton() {
  return (
    <div className="space-y-8 sm:space-y-10">
      <GreetingSkeleton />
      <SynthesisSkeleton />
      <CardsGridSkeleton />
    </div>
  );
}
