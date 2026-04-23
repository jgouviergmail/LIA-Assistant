'use client';

import { useTranslation } from 'react-i18next';
import { useBriefing } from '@/hooks/useBriefing';
import { BriefingError } from './BriefingError';
import { BriefingGreeting } from './BriefingGreeting';
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
import { CardsGridSkeleton, GreetingSkeleton, SynthesisSkeleton } from './BriefingSkeleton';

/**
 * Today briefing — orchestrates the full home page flow with NON-BLOCKING rendering.
 *
 * Two independent network queries (see useBriefing) — the page renders progressively:
 *  1. Cards arrive first (fast, no LLM) → grid + Quick Access + Hero shown immediately
 *  2. Greeting + synthesis arrive later (LLM-bound) → swap from skeleton to text
 *
 * Layout (top → bottom):
 *   1. Greeting (LLM, sober single sentence)
 *   2. Synthesis (LLM, glass card with primary accent)
 *   3. Hero LIA (preserved marketing card)
 *   4. Quick Access (Help + Settings — ABOVE the dashboard cards)
 *   5. "Mon dashboard" 6-card grid
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
      {/* Greeting: skeleton during LLM call → real text once arrived */}
      {text ? <BriefingGreeting greeting={text.greeting} /> : <GreetingSkeleton />}

      <HeroLiaCard />

      {/* Quick Access — placed ABOVE the cards grid as requested */}
      <QuickAccessCompact />

      <section className="space-y-4" aria-labelledby="briefing-section-heading">
        <div className="flex items-center justify-between">
          <h2
            id="briefing-section-heading"
            className="text-base sm:text-lg font-semibold tracking-tight text-foreground"
          >
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
