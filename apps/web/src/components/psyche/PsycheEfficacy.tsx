'use client';

import {
  ShieldCheck,
  type LucideIcon,
  Compass,
  Search,
  Heart,
  Palette,
  Wrench,
  Users,
  ListChecks,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Disclosure } from '@/components/ui/disclosure';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import type { Language } from '@/i18n/settings';
import {
  EFFICACY_DOMAINS,
  type EfficacyDomain,
  type PsycheEfficacyDomain,
  type PsycheEfficacyProfile,
} from '@/types/psyche';

const DOMAIN_ICONS: Record<EfficacyDomain, LucideIcon> = {
  planning: Compass,
  information: Search,
  emotional_support: Heart,
  creativity: Palette,
  technical: Wrench,
  social: Users,
  organization: ListChecks,
};

function unobservedDomain(domain: EfficacyDomain): PsycheEfficacyDomain {
  return {
    domain,
    status: 'unobserved',
    results: { success: 0, failure: 0, partial: 0, unknown: 0 },
    feedback: { helpful: 0, unhelpful: 0 },
    result_count: 0,
    feedback_count: 0,
    result_score: null,
    feedback_score: null,
    last_observed_at: null,
  };
}

function observationDate(value: string | null, lng: Language, timezone: string | undefined) {
  if (!value || !timezone) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return null;
  try {
    return new Intl.DateTimeFormat(lng, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: timezone,
    }).format(date);
  } catch {
    // Never substitute the host/browser zone for an unknown account zone.
    return null;
  }
}

export function PsycheEfficacy({
  profile,
  lng,
}: {
  profile?: PsycheEfficacyProfile | null;
  lng: Language;
}) {
  const { t } = useTranslation(lng, 'translation');
  const { user } = useAuth();
  return (
    <Disclosure
      defaultOpen
      surface="nested"
      icon={ShieldCheck}
      title={t('psyche.education.drives.efficacy_title')}
      titleClassName="whitespace-normal text-base font-semibold"
      className="border-border px-4 sm:px-6"
    >
      <div className="space-y-4 pt-2">
        {profile ? (
          <div className="space-y-2 text-xs text-muted-foreground">
            <p>{t('psyche.efficacy.window', { days: profile.window_days })}</p>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span>
                {t(
                  profile.collection_enabled
                    ? 'psyche.efficacy.collectionOn'
                    : 'psyche.efficacy.collectionOff'
                )}
              </span>
              <span>
                {t(
                  profile.influence_enabled
                    ? 'psyche.efficacy.influenceOn'
                    : 'psyche.efficacy.influenceOff'
                )}
              </span>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('psyche.efficacy.noEvidence')}</p>
        )}
        <div className="space-y-3">
          {EFFICACY_DOMAINS.map(domain => (
            <DomainEvidence
              key={domain}
              domain={domain}
              entry={
                profile?.domains.find(entry => entry.domain === domain) ?? unobservedDomain(domain)
              }
              lng={lng}
              timezone={user?.timezone}
            />
          ))}
        </div>
        {!!profile?.unassigned_feedback_count && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t('psyche.efficacy.unassigned', { count: profile.unassigned_feedback_count })}
          </p>
        )}
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('psyche.efficacy.indicesHint')}
        </p>
      </div>
    </Disclosure>
  );
}

function DomainEvidence({
  domain,
  entry,
  lng,
  timezone,
}: {
  domain: EfficacyDomain;
  entry: PsycheEfficacyDomain;
  lng: Language;
  timezone?: string;
}) {
  const { t } = useTranslation(lng, 'translation');
  const title = t(`psyche.domains.${domain}`);
  const Icon = DOMAIN_ICONS[domain];
  const hasEvidence =
    entry.result_count > 0 ||
    entry.feedback_count > 0 ||
    entry.results.partial > 0 ||
    entry.results.unknown > 0;
  const date = observationDate(entry.last_observed_at, lng, timezone);
  return (
    <section
      aria-label={title}
      className="min-w-0 rounded-lg border border-border bg-card px-3 py-3 sm:px-4"
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <h4 className="flex min-w-0 items-center gap-2 text-sm font-semibold">
          <Icon aria-hidden="true" className="size-4 shrink-0 text-primary" />
          <span className="min-w-0 break-words">{title}</span>
        </h4>
        <Badge
          variant={entry.status === 'observed' ? 'default' : 'outline'}
          className="shrink-0 text-xs font-normal"
        >
          {t(`psyche.efficacy.status.${entry.status}`)}
        </Badge>
      </div>
      {hasEvidence && (
        <div className="mt-4 grid min-w-0 gap-4 md:grid-cols-2 md:gap-6">
          <EvidenceAxis
            name={`${title} · ${t('psyche.efficacy.results')}`}
            title={t('psyche.efficacy.results')}
            score={entry.result_score}
            count={entry.result_count}
            basis={t('psyche.efficacy.resultBasis', { count: entry.result_count })}
            detail={t('psyche.efficacy.resultDetail', {
              success: entry.results.success,
              failure: entry.results.failure,
            })}
            supplementary={t('psyche.efficacy.otherResults', {
              partial: entry.results.partial,
              unknown: entry.results.unknown,
            })}
            lng={lng}
          />
          <EvidenceAxis
            name={`${title} · ${t('psyche.efficacy.usefulness')}`}
            title={t('psyche.efficacy.usefulness')}
            score={entry.feedback_score}
            count={entry.feedback_count}
            basis={t('psyche.efficacy.feedbackBasis', { count: entry.feedback_count })}
            detail={t('psyche.efficacy.feedbackDetail', {
              helpful: entry.feedback.helpful,
              unhelpful: entry.feedback.unhelpful,
            })}
            lng={lng}
          />
        </div>
      )}
      {date && (
        <p className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground">
          {t('psyche.efficacy.lastObserved', { date })}
        </p>
      )}
    </section>
  );
}

function EvidenceAxis({
  name,
  title,
  score,
  count,
  basis,
  detail,
  supplementary,
  lng,
}: {
  name: string;
  title: string;
  score: number | null;
  count: number;
  basis: string;
  detail: string;
  supplementary?: string;
  lng: Language;
}) {
  const { t } = useTranslation(lng, 'translation');
  const valid = count > 0 && score !== null && Number.isFinite(score) && score >= 0 && score <= 1;
  const percent = valid ? Math.round(score * 100) : null;
  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex items-start justify-between gap-2 text-sm">
        <span>{title}</span>
        <span className="shrink-0 font-semibold tabular-nums text-primary">
          {percent === null ? '—' : `${percent} %`}
        </span>
      </div>
      {percent !== null && (
        <p className="text-xs text-muted-foreground">{t('psyche.efficacy.smoothedIndex')}</p>
      )}
      {percent !== null && (
        <div
          role="meter"
          aria-label={name}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-valuetext={`${percent} % · ${basis}`}
          className="h-1.5 overflow-hidden rounded-full bg-primary/10"
        >
          <div
            aria-hidden="true"
            className="h-full rounded-full bg-primary/70"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {count > 0 ? basis : t('psyche.efficacy.noBasis')}
      </p>
      {count > 0 && <p className="text-xs leading-relaxed text-muted-foreground">{detail}</p>}
      {supplementary && (
        <p className="text-xs leading-relaxed text-muted-foreground">{supplementary}</p>
      )}
    </div>
  );
}
