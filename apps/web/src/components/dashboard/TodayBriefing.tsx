'use client';

import { Sunrise } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useBriefing } from '@/hooks/useBriefing';
import { BriefingError } from './BriefingError';
import { BriefingSynthesis } from './BriefingSynthesis';
import { HeroLiaCard } from './HeroLiaCard';
import { QuickAccessCompact } from './QuickAccessCompact';
import { RefreshAllButton } from './RefreshAllButton';
import { AgendaCard } from './cards/AgendaCard';
import { BirthdaysCard } from './cards/BirthdaysCard';
import { HealthCard } from './cards/HealthCard';
import { MailsCard } from './cards/MailsCard';
import { RemindersCard } from './cards/RemindersCard';
import { WeatherCard } from './cards/WeatherCard';
import { CardsGridSkeleton, SynthesisSkeleton } from './BriefingSkeleton';

/**
 * Today briefing — orchestrates the full home page flow with NON-BLOCKING rendering.
 *
 * Two independent network queries (see useBriefing) — the page renders progressively:
 *  1. Cards arrive first (fast, no LLM) → grid + Quick Access + Hero shown immediately
 *  2. Greeting + synthesis arrive later (LLM-bound) → swap from fallback to LLM text
 *
 * Layout (top → bottom):
 *   1. Hero LIA (marketing card — its headline is the LLM greeting once it arrives,
 *      a static localized tagline as fallback while the LLM call is in flight)
 *   2. Quick Access (Help + Settings)
 *   3. "Mon dashboard" 6-card grid (with the synthesis above the cards)
 */
export function TodayBriefing() {
  const { t } = useTranslation();
  const {
    cards,
    text,
    cardsLoading,
    textLoading,
    error,
    refetchAll,
    refetchSection,
    refreshingSections,
  } = useBriefing();

  // Page-level error only when BOTH queries fail without any data — otherwise
  // each section renders independently (errors handled per-card).
  if (error && !cards && !text) return <BriefingError onRetry={refetchAll} />;

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* Hero — headline swaps from fallback tagline to LLM greeting once ready */}
      <HeroLiaCard
        greeting={text?.greeting ?? null}
        isLoadingGreeting={textLoading}
      />

      {/* Quick Access — placed ABOVE the cards grid as requested */}
      <QuickAccessCompact />

      <section className="space-y-4" aria-labelledby="briefing-section-heading">
        <div className="flex items-center justify-between">
          <h2
            id="briefing-section-heading"
            className="flex items-center gap-2 text-base sm:text-lg font-semibold tracking-tight text-foreground"
          >
            <Sunrise className="h-5 w-5 text-primary shrink-0" aria-hidden="true" />
            {t('dashboard.briefing.section_title')}
          </h2>
          <RefreshAllButton
            onClick={() => refetchSection('all')}
            isRefreshing={refreshingSections.has('all')}
          />
        </div>

        {/* Synthesis: placed UNDER section title, ABOVE the cards grid */}
        {text ? (
          text.synthesis ? <BriefingSynthesis synthesis={text.synthesis} /> : null
        ) : (
          textLoading ? <SynthesisSkeleton /> : null
        )}

        {/* Cards: skeleton during initial load → real cards once arrived */}
        {cards ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
            <WeatherCard
              section={cards.weather}
              isRefreshing={refreshingSections.has('weather')}
              onRefresh={() => refetchSection('weather')}
              staggerIndex={0}
            />
            <BirthdaysCard
              section={cards.birthdays}
              isRefreshing={refreshingSections.has('birthdays')}
              onRefresh={() => refetchSection('birthdays')}
              staggerIndex={1}
            />
            <RemindersCard
              section={cards.reminders}
              isRefreshing={refreshingSections.has('reminders')}
              onRefresh={() => refetchSection('reminders')}
              staggerIndex={2}
            />
            <HealthCard
              section={cards.health}
              isRefreshing={refreshingSections.has('health')}
              onRefresh={() => refetchSection('health')}
              staggerIndex={3}
            />
            <AgendaCard
              section={cards.agenda}
              isRefreshing={refreshingSections.has('agenda')}
              onRefresh={() => refetchSection('agenda')}
              staggerIndex={4}
            />
            <MailsCard
              section={cards.mails}
              isRefreshing={refreshingSections.has('mails')}
              onRefresh={() => refetchSection('mails')}
              staggerIndex={5}
            />
          </div>
        ) : (
          cardsLoading ? <CardsGridSkeleton /> : null
        )}
      </section>
    </div>
  );
}
