'use client';

import { useTranslation } from 'react-i18next';
import { AnimatedCounter } from './AnimatedCounter';
import { LANDING_STATS } from './constants';

const STATS = [
  { value: LANDING_STATS.agents, suffix: '+', key: 'agents' },
  { value: LANDING_STATS.tools, suffix: '+', key: 'tools' },
  { value: LANDING_STATS.providers, suffix: '', key: 'providers' },
  { value: LANDING_STATS.voiceLanguages, suffix: '+', key: 'voice_languages' },
  { value: LANDING_STATS.metrics, suffix: '+', key: 'metrics' },
  { value: LANDING_STATS.uiLanguages, suffix: '', key: 'ui_languages' },
] as const;

export function StatsSection() {
  const { t } = useTranslation();

  return (
    <section className="py-16 bg-primary/5" aria-label={t('landing.features.title')}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 sm:grid-cols-3 mobile:grid-cols-6 gap-8">
          {STATS.map(({ value, suffix, key }) => (
            <div key={key} className="text-center">
              <div className="text-3xl mobile:text-4xl font-bold text-foreground">
                <AnimatedCounter target={value} suffix={suffix} />
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {t(`landing.stats.${key}`)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
