'use client';

/**
 * RelationDetailPanel — the 360° view of one relationship (N-09, restyled).
 *
 * Identity header (large avatar, peers badge, star) over sectioned CARDS —
 * open loops with an age pill, dated calls, memories as bordered notes.
 * Read-only aggregation; the ONE action is "prepare a 360° point", a chat
 * `?intent=` deep link (ADR-173). The best-effort identity match is stated,
 * never hidden (honesty rule).
 */

import { ArrowLeft, Handshake, ListTodo, PhoneCall, Sparkles, Star, StickyNote } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RelationAvatar } from '@/components/relations/RelationAvatar';
import { chatIntentHref, timeAgoLabel } from '@/lib/briefing-utils';
import { useRelationDetail } from '@/hooks/useRelations';

function SectionCard({
  icon: Icon,
  title,
  count,
  children,
}: {
  icon: typeof Handshake;
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border/50 bg-card p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        {title}
        <span className="rounded-full bg-muted px-2 py-px text-[11px] font-medium tabular-nums text-muted-foreground">
          {count}
        </span>
      </h3>
      <div className="mt-3 space-y-2.5">{children}</div>
    </section>
  );
}

export function RelationDetailPanel({
  name,
  lng,
  isFavorite,
  onToggleFavorite,
  onBack,
}: {
  name: string;
  lng: string;
  /** Star state from the overview (single source; the panel never re-reads). */
  isFavorite: boolean;
  onToggleFavorite: (name: string, nextValue: boolean) => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const { detail, loading } = useRelationDetail(name);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner className="h-6 w-6" />
      </div>
    );
  }
  if (!detail) return null;

  const prepIntent = t('relations.prepare_intent', { name: detail.display_name });
  const starLabel = isFavorite
    ? t('relations.favorite_remove', { name: detail.display_name })
    : t('relations.favorite_add', { name: detail.display_name });
  const isEmpty =
    detail.open_loops.length === 0 &&
    detail.recent_calls.length === 0 &&
    detail.memories.length === 0;

  return (
    <div className="space-y-5">
      {/* Identity header: avatar + name + badges left, actions right. */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/50 bg-card p-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            aria-label={t('relations.back')}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <RelationAvatar name={detail.display_name} size="lg" />
          <div className="min-w-0">
            <span className="flex items-center gap-2">
              <h2 className="truncate text-xl font-bold tracking-tight">
                {detail.display_name}
              </h2>
              {detail.is_peer && (
                <span
                  className="inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary"
                  title={t('relations.peer_badge_hint')}
                >
                  <Handshake className="h-3 w-3" aria-hidden="true" />
                  {t('relations.peer_badge')}
                </span>
              )}
            </span>
            <p className="text-xs text-muted-foreground">{t('relations.subtitle_detail')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onToggleFavorite(detail.display_name, !isFavorite)}
            aria-label={starLabel}
            aria-pressed={isFavorite}
            className="rounded-full border border-border/60 p-2 transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Star
              aria-hidden="true"
              className={cn(
                'h-4 w-4',
                isFavorite ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/60'
              )}
            />
          </button>
          <button
            type="button"
            onClick={() => router.push(chatIntentHref(lng, prepIntent))}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            {t('relations.prepare_360')}
          </button>
        </div>
      </div>

      {/* Best-effort caveat: shown on a normalized name match OR whenever a
          memory is attached — memories are matched by name substring, which
          can over-match even on an EXACT loop/call identity (a common first
          name landing in an unrelated note). Honesty over false precision. */}
      {(detail.identity_confidence === 'normalized' || detail.memories.length > 0) && (
        <p className="rounded-md border border-border/40 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {t('relations.identity_best_effort')}
        </p>
      )}

      {detail.open_loops.length > 0 && (
        <SectionCard
          icon={ListTodo}
          title={t('relations.section_open_loops')}
          count={detail.open_loops.length}
        >
          {detail.open_loops.map(loop => (
            <p
              key={loop.id}
              className="flex flex-wrap items-baseline gap-2 border-l-2 border-amber-500/40 pl-3 text-sm text-foreground/90"
            >
              {loop.subject}
              <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-px text-[10px] font-medium text-amber-700 dark:text-amber-300">
                {t('relations.days_open', { count: loop.days_open })}
              </span>
            </p>
          ))}
        </SectionCard>
      )}

      {detail.recent_calls.length > 0 && (
        <SectionCard
          icon={PhoneCall}
          title={t('relations.section_calls')}
          count={detail.recent_calls.length}
        >
          {detail.recent_calls.map(call => (
            <div key={call.id} className="border-l-2 border-sky-500/40 pl-3">
              <p className="flex flex-wrap items-baseline gap-2 text-sm text-foreground/90">
                {call.objective}
                <span className="text-[11px] text-muted-foreground">
                  {timeAgoLabel(t, call.created_at)}
                </span>
              </p>
              {call.summary && (
                <p className="mt-0.5 text-xs text-muted-foreground">{call.summary}</p>
              )}
            </div>
          ))}
        </SectionCard>
      )}

      {detail.memories.length > 0 && (
        <SectionCard
          icon={StickyNote}
          title={t('relations.section_memories')}
          count={detail.memories.length}
        >
          {detail.memories.map(memory => (
            <p
              key={memory.id}
              className="rounded-lg border border-border/40 bg-muted/30 px-3 py-2 text-sm text-foreground/90"
            >
              {memory.content}
            </p>
          ))}
        </SectionCard>
      )}

      {isEmpty && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {t('relations.detail_empty')}
        </p>
      )}
    </div>
  );
}
