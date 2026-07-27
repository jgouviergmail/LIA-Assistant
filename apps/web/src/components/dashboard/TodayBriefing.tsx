'use client';

import Link from 'next/link';
import { Sunrise } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useBriefing } from '@/hooks/useBriefing';
import { useBriefingPreferences } from '@/hooks/useBriefingPreferences';
import type { BriefingPreferences, BriefingSection, CardsBundle } from '@/types/briefing';
import { BriefingError } from './BriefingError';
import { BriefingSynthesis } from './BriefingSynthesis';
import { HeroLiaCard } from './HeroLiaCard';
import { PortraitHint } from './PortraitHint';
import { StarterChecklistCard } from './StarterChecklistCard';
import { InstallHint } from '@/components/pwa/InstallHint';
import { QuickAccessCompact } from './QuickAccessCompact';
import { RefreshAllButton } from './RefreshAllButton';
import { BriefingSetupHint } from './BriefingSetupHint';
import { unconfiguredCards } from '@/lib/briefing-setup';
import { AgendaCard } from './cards/AgendaCard';
import { BirthdaysCard } from './cards/BirthdaysCard';
import { DocumentsCard } from './cards/DocumentsCard';
import { ForYouCard } from './cards/ForYouCard';
import { TasksCard } from './cards/TasksCard';
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
 *   3. "Mon dashboard" 9-card grid (with the synthesis above the cards)
 */
/**
 * Ordered VISIBLE sections (UXR Lot 5, B4) — pure, pinned by tests: the
 * stored order filtered by the hidden set; a `hidden` status from the
 * backend is skipped too (belt and braces — the two must agree).
 */
export function visibleOrderedSections(
  preferences: BriefingPreferences | null,
  cards: CardsBundle
): BriefingSection[] {
  const order = preferences?.order?.length
    ? preferences.order
    : (Object.keys(CARD_RENDERERS) as BriefingSection[]);
  const hidden = new Set(preferences?.hidden ?? []);
  return order.filter(name => !hidden.has(name) && cards[name]?.status !== 'hidden');
}

/** One renderer per section — completeness vs the 9 names pinned by test. */
const CARD_RENDERERS: Record<
  BriefingSection,
  (
    cards: CardsBundle,
    common: { isRefreshing: boolean; onRefresh: () => void; staggerIndex: number }
  ) => React.ReactElement
> = {
  weather: (c, p) => <WeatherCard section={c.weather} {...p} />,
  birthdays: (c, p) => <BirthdaysCard section={c.birthdays} {...p} />,
  reminders: (c, p) => <RemindersCard section={c.reminders} {...p} />,
  health: (c, p) => <HealthCard section={c.health} {...p} />,
  agenda: (c, p) => <AgendaCard section={c.agenda} {...p} />,
  mails: (c, p) => <MailsCard section={c.mails} {...p} />,
  for_you: (c, p) => <ForYouCard section={c.for_you} {...p} />,
  tasks: (c, p) => <TasksCard section={c.tasks} {...p} />,
  documents: (c, p) => <DocumentsCard section={c.documents} {...p} />,
};

/**
 * The preference-ordered grid (extracted — CC discipline). All cards hidden
 * → a discreet CTA to the settings instead of an empty grid.
 */
function BriefingCardsGrid({
  cards,
  sections,
  refreshingSections,
  refetchSection,
  settingsHref,
  lng,
}: {
  cards: CardsBundle;
  sections: BriefingSection[];
  refreshingSections: Set<string>;
  refetchSection: (section: BriefingSection) => void;
  settingsHref: string;
  lng: string;
}) {
  const { t } = useTranslation();
  if (sections.length === 0) {
    return (
      <p className="px-1 text-sm italic text-muted-foreground">
        {t('dashboard.briefing.all_hidden')}{' '}
        <Link
          href={settingsHref}
          className="font-semibold text-primary underline decoration-primary/40 hover:text-primary/80"
        >
          {t('dashboard.briefing.all_hidden_cta')}
        </Link>
      </p>
    );
  }
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        {sections.map((name, index) => (
          <div key={name} className="contents">
            {CARD_RENDERERS[name](cards, {
              isRefreshing: refreshingSections.has(name),
              onRefresh: () => refetchSection(name),
              staggerIndex: index,
            })}
          </div>
        ))}
      </div>
      {/* W7: a card with no source renders NOTHING (BriefingCard returns null),
          so an unconfigured account used to face silent holes. Name them once,
          below the grid, each linking to the settings that fill it. */}
      <BriefingSetupHint cards={unconfiguredCards(cards, sections)} lng={lng} />
    </>
  );
}

export function TodayBriefing() {
  const { t, i18n } = useTranslation();
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
  // UXR Lot 5 (B4): grid preferences (visibility + order) — NULL/loading
  // falls back to the historical layout inside visibleOrderedSections.
  const { preferences } = useBriefingPreferences();
  const lng = (i18n.language || 'fr').split('-')[0];

  // Page-level error only when BOTH queries fail without any data — otherwise
  // each section renders independently (errors handled per-card).
  if (error && !cards && !text) return <BriefingError onRetry={refetchAll} />;

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* Hero — headline swaps from fallback tagline to LLM greeting once ready */}
      <HeroLiaCard greeting={text?.greeting ?? null} isLoadingGreeting={textLoading} />

      {/* QW-10: discreet "I refined my understanding of you" line when the
          portrait was recompiled recently (renders nothing otherwise). */}
      <PortraitHint />

      {/* UXR Lot 6 (A10): dismissible "getting started" checklist — renders
          nothing once dismissed or celebrated. */}
      <StarterChecklistCard />

      {/* UXR Lot 9 (A6): contextual PWA install nudge (≥3 visits, never in
          standalone, dismissible forever). */}
      <InstallHint />

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

        {/* Synthesis: placed UNDER section title, ABOVE the cards grid.
            When the LLM call returns null (legitimate skip due to <2 cards
            with data, or transient LLM failure) we surface a discreet
            single-line fallback so the slot is not silently empty. */}
        {text ? (
          text.synthesis ? (
            <BriefingSynthesis synthesis={text.synthesis} />
          ) : (
            <p className="px-1 text-sm italic text-muted-foreground" role="status">
              {t('dashboard.briefing.synthesis_unavailable')}
            </p>
          )
        ) : textLoading ? (
          <SynthesisSkeleton />
        ) : null}

        {/* Cards (UXR Lot 5, B4): ordered by the user's preferences, hidden
            cards never rendered (and never fetched backend-side). */}
        {cards ? (
          <BriefingCardsGrid
            cards={cards}
            sections={visibleOrderedSections(preferences, cards)}
            refreshingSections={refreshingSections}
            refetchSection={refetchSection}
            settingsHref={`/${lng}/dashboard/settings`}
            lng={lng}
          />
        ) : cardsLoading ? (
          <CardsGridSkeleton />
        ) : null}
      </section>
    </div>
  );
}
