'use client';

/**
 * The one line that names the missing cards (W7).
 *
 * Seven of the nine briefing cards vanish silently when their source is not
 * configured (`BriefingCard` returns `null`). For a fresh account that means a
 * first screen with two empty cards and seven invisible holes — no card, no
 * message, no way to know anything is missing.
 *
 * The fix is deliberately ONE line, not seven placeholder cards: on mobile the
 * grid is already the whole screen, and seven "connect me" tiles would push the
 * real content below the fold to advertise features the user never asked for.
 * Each card name links straight to the settings section that configures it, so
 * the shortest possible text is also the most actionable.
 *
 * Cards the user has HIDDEN are never mentioned — that is handled upstream by
 * `unconfiguredCards`, which only ever sees the visible ones.
 */

import Link from 'next/link';
import { Settings2 } from 'lucide-react';

import { useTranslation } from 'react-i18next';

import { settingsSectionHref } from '@/lib/settings-sections';
import { type UnconfiguredCard } from '@/lib/briefing-setup';

export interface BriefingSetupHintProps {
  /** Visible cards waiting for a configuration, in grid order. */
  cards: readonly UnconfiguredCard[];
  /** Current URL locale segment. */
  lng: string;
}

export function BriefingSetupHint({ cards, lng }: BriefingSetupHintProps) {
  const { t } = useTranslation();

  // Everything configured: the line does not exist at all. No empty container,
  // no reserved space.
  if (cards.length === 0) return null;

  return (
    <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 px-1 text-sm text-muted-foreground">
      <Settings2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{t('dashboard.briefing.not_configured_intro', { count: cards.length })}</span>
      {cards.map(({ section, target }, index) => {
        const label = t(`dashboard.briefing.sections.${section}.title`);
        return (
          <span key={section} className="inline-flex items-center">
            {target ? (
              <Link
                href={settingsSectionHref(lng, target)}
                className="font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:text-primary/80 hover:decoration-primary rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                // The name alone ("Agenda") does not say what following it does.
                aria-label={t('dashboard.briefing.not_configured_cta', { card: label })}
              >
                {label}
              </Link>
            ) : (
              // No known destination: name it, but never fake a link.
              <span className="font-medium">{label}</span>
            )}
            {index < cards.length - 1 && (
              <span aria-hidden="true" className="ml-1.5 text-muted-foreground/60">
                ·
              </span>
            )}
          </span>
        );
      })}
    </p>
  );
}
