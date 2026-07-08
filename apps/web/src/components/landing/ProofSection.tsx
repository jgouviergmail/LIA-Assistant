'use client';

import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { ArrowRight, BadgeCheck } from 'lucide-react';
import { AnimatedCounter } from './AnimatedCounter';
import { LANDING_STATS } from './constants';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

interface ProofSectionProps {
  lng: string;
}

/**
 * Proof band — verifiable product and engineering numbers, directly under
 * the hero. Doubles as the teaser for the /story field report: every figure
 * here is backed by the public repository or the published audit.
 */
export function ProofSection({ lng }: ProofSectionProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const productStats = [
    { value: LANDING_STATS.agents, suffix: '+', key: 'agents' },
    { value: LANDING_STATS.tools, suffix: '', key: 'tools' },
    { value: LANDING_STATS.providers, suffix: '', key: 'providers' },
    { value: LANDING_STATS.voiceLanguages, suffix: '+', key: 'voice_languages' },
  ] as const;

  const engineeringStats = [
    { value: LANDING_STATS.tests, suffix: '+', key: 'tests', localized: true },
    { value: LANDING_STATS.adrs, suffix: '+', key: 'adrs', localized: false },
    { value: LANDING_STATS.releases, suffix: '+', key: 'releases', localized: false },
  ] as const;

  return (
    <section id="proof" className="py-16 bg-primary/5" aria-labelledby="proof-title">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 id="proof-title" className="sr-only">
          {t('landing.proof.title')}
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 mobile:grid-cols-8 gap-x-6 gap-y-8">
          {productStats.map(({ value, suffix, key }) => (
            <div key={key} className="text-center">
              <div className="text-3xl mobile:text-4xl font-bold text-foreground">
                <AnimatedCounter target={value} suffix={suffix} />
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {t(`landing.proof.items.${key}`)}
              </div>
            </div>
          ))}

          {engineeringStats.map(({ value, suffix, key, localized }) => (
            <div key={key} className="text-center">
              <div className="text-3xl mobile:text-4xl font-bold text-foreground">
                <AnimatedCounter
                  target={value}
                  suffix={suffix}
                  locale={localized ? locale : undefined}
                />
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {t(`landing.proof.items.${key}`)}
              </div>
            </div>
          ))}

          {/* Audit score — string value, not a counter */}
          <div className="text-center">
            <div className="text-3xl mobile:text-4xl font-bold text-primary inline-flex items-center gap-1.5">
              <BadgeCheck className="w-6 h-6 mobile:w-7 mobile:h-7" aria-hidden="true" />
              {t('landing.proof.audit_value')}
            </div>
            <div className="text-sm text-muted-foreground mt-1">
              {t('landing.proof.items.audit')}
            </div>
          </div>
        </div>

        {/* Field-report teaser */}
        <p className="text-center text-sm text-muted-foreground mt-10">
          {t('landing.proof.rex_teaser')}{' '}
          <Link
            href={buildLocalizedPath('/story', lng as Language)}
            className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
          >
            {t('landing.proof.rex_link')}
            <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </Link>
        </p>
      </div>
    </section>
  );
}
