'use client';

/**
 * RelationDetailPanel — the 360° view of one relationship (N-09).
 *
 * Read-only aggregation; the ONE action is "prepare a 360° point", a chat
 * `?intent=` deep link (ADR-173 — executed by the chat pipeline). The
 * best-effort identity match is stated, never hidden (honesty rule).
 */

import { ArrowLeft, Handshake, PhoneCall, Sparkles, StickyNote } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { chatIntentHref } from '@/lib/briefing-utils';
import { useRelationDetail } from '@/hooks/useRelations';

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Handshake;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        {title}
      </h3>
      <div className="mt-2 space-y-1.5">{children}</div>
    </div>
  );
}

export function RelationDetailPanel({
  name,
  lng,
  onBack,
}: {
  name: string;
  lng: string;
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

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            aria-label={t('relations.back')}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <h2 className="text-xl font-bold tracking-tight">{detail.display_name}</h2>
        </div>
        <button
          type="button"
          onClick={() => router.push(chatIntentHref(lng, prepIntent))}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {t('relations.prepare_360')}
        </button>
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
        <Section icon={Handshake} title={t('relations.section_open_loops')}>
          {detail.open_loops.map(loop => (
            <p key={loop.id} className="text-sm text-foreground/90">
              {loop.subject}
              <span className="ml-2 text-xs text-muted-foreground">
                {t('relations.days_open', { count: loop.days_open })}
              </span>
            </p>
          ))}
        </Section>
      )}

      {detail.recent_calls.length > 0 && (
        <Section icon={PhoneCall} title={t('relations.section_calls')}>
          {detail.recent_calls.map(call => (
            <p key={call.id} className="text-sm text-foreground/90">
              {call.objective}
              {call.summary && (
                <span className="block text-xs text-muted-foreground">{call.summary}</span>
              )}
            </p>
          ))}
        </Section>
      )}

      {detail.memories.length > 0 && (
        <Section icon={StickyNote} title={t('relations.section_memories')}>
          {detail.memories.map(memory => (
            <p key={memory.id} className="text-sm text-foreground/90">
              {memory.content}
            </p>
          ))}
        </Section>
      )}

      {detail.open_loops.length === 0 &&
        detail.recent_calls.length === 0 &&
        detail.memories.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {t('relations.detail_empty')}
          </p>
        )}
    </div>
  );
}
