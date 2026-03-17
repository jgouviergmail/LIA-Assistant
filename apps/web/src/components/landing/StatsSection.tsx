'use client';

import { useTranslation } from 'react-i18next';
import { AnimatedCounter } from './AnimatedCounter';

const STATS = [
  { value: 17, suffix: '+', key: 'agents' },
  { value: 50, suffix: '+', key: 'tools' },
  { value: 6, suffix: '', key: 'providers' },
  { value: 99, suffix: '+', key: 'voice_languages' },
  { value: 500, suffix: '+', key: 'metrics' },
  { value: 6, suffix: '', key: 'ui_languages' },
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
