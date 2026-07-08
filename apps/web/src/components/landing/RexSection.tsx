import Link from 'next/link';
import { initI18next } from '@/i18n';
import { Button } from '@/components/ui/button';
import { ArrowRight } from 'lucide-react';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { FadeInOnScroll } from './FadeInOnScroll';

interface RexSectionProps {
  lng: string;
}

const KPI_KEYS = ['lines', 'ai', 'tests', 'audit'] as const;

/**
 * Field-report section — how LIA was built: ~100% AI-written code under
 * human direction, measured by a public audit. Links to the full /story page.
 */
export async function RexSection({ lng }: RexSectionProps) {
  const { t } = await initI18next(lng);
  const storyHref = buildLocalizedPath('/story', lng as Language);

  return (
    <section id="story" className="landing-section py-20 bg-card" aria-labelledby="rex-title">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <FadeInOnScroll>
          <p className="text-sm font-semibold uppercase tracking-widest text-primary mb-3">
            {t('landing.rex.eyebrow')}
          </p>
          <h2 id="rex-title" className="text-3xl mobile:text-4xl font-bold tracking-tight mb-8">
            {t('landing.rex.title')}
          </h2>

          {/* Signature quote */}
          <blockquote className="relative max-w-2xl mx-auto mb-10">
            <span
              className="absolute -top-6 -left-2 text-7xl font-serif text-primary/20 select-none"
              aria-hidden="true"
            >
              &ldquo;
            </span>
            <p className="text-xl mobile:text-2xl font-medium leading-relaxed italic text-foreground/90">
              {t('landing.rex.quote')}
            </p>
          </blockquote>

          {/* KPIs */}
          <div className="grid grid-cols-2 mobile:grid-cols-4 gap-4 mb-10">
            {KPI_KEYS.map(key => (
              <div
                key={key}
                className="rounded-xl border border-border/60 bg-background px-4 py-5"
              >
                <div className="text-2xl mobile:text-3xl font-bold text-primary tabular-nums">
                  {t(`landing.rex.kpis.${key}.value`)}
                </div>
                <div className="text-xs text-muted-foreground mt-1 leading-snug">
                  {t(`landing.rex.kpis.${key}.label`)}
                </div>
              </div>
            ))}
          </div>

          <p className="text-muted-foreground max-w-2xl mx-auto leading-relaxed mb-8">
            {t('landing.rex.body')}
          </p>

          <Button asChild size="lg" variant="outline" className="gap-2">
            <Link href={storyHref}>
              {t('landing.rex.cta')}
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Link>
          </Button>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
