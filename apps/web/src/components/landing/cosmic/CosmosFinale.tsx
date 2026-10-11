'use client';

/**
 * Cosmic finale: homepage-specific CTA content, register
 * link, LIA's last-word bubble) above a clean planet horizon (deep sphere,
 * drifting clouds).
 */

import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PlayCircle } from 'lucide-react';
import { getPublicShowroomVariant } from '@/lib/showroom-config';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { GhostWord } from './GhostWord';

export function CosmosFinale({ lng }: { lng: string }) {
  const { t } = useTranslation();
  const registerHref = buildLocalizedPath('/register', lng as Language);
  const whyHref = buildLocalizedPath('/why', lng as Language);
  const demoHref = buildLocalizedPath('/demo', lng as Language);
  const showsGuidedDemo = getPublicShowroomVariant() === 'guided';

  return (
    <section
      aria-labelledby="cosmos-cta-title"
      className="cosmos-finale landing-section relative overflow-clip pt-24 text-center"
    >
      <GhostWord wordKey="landing.cosmos.ghost.cta" direction={1} className="cosmos-ghost-high" />
      <div className="relative z-10 max-w-3xl mx-auto px-4">
        <Badge className="mb-6">{t('landing.hero.badge_beta')}</Badge>
        {/* Signature device carried to the very end: LIA gets the last word */}
        <div className="mb-6 flex items-start justify-center gap-2.5" aria-hidden="true">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-card text-base leading-none">
            😏
          </span>
          <span className="rounded-2xl rounded-tl-[5px] border border-border bg-card px-3.5 py-2 text-sm italic text-muted-foreground">
            {t('landing.home_cta.bubble')}
          </span>
        </div>
        <h2
          id="cosmos-cta-title"
          className="text-3xl mobile:text-4xl lg:text-5xl font-extrabold tracking-tight mb-6"
        >
          {t('landing.home_cta.title')}
        </h2>
        <p className="text-lg text-muted-foreground mb-8 max-w-xl mx-auto">
          {t('landing.home_cta.subtitle')}
        </p>
        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row sm:flex-wrap">
          {showsGuidedDemo && (
            <Button asChild size="lg" className="w-full gap-2 text-base px-6 sm:w-auto">
              <Link href={demoHref}>
                <PlayCircle className="size-5" aria-hidden="true" />
                {t('landing.hero.home_cta_demo')}
              </Link>
            </Button>
          )}
          <Button
            asChild
            variant={showsGuidedDemo ? 'outline' : 'default'}
            size="lg"
            className="w-full text-base px-6 font-semibold sm:w-auto"
          >
            <Link href={registerHref}>{t('landing.home_cta.button')}</Link>
          </Button>
        </div>
        <a
          href="https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/GETTING_STARTED.md"
          target="_blank"
          rel="noopener noreferrer"
          className="mx-auto mt-4 block w-fit rounded-sm text-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t('landing.home_cta.install_link')}
        </a>
        <p className="text-sm text-muted-foreground mt-6">{t('landing.home_cta.note_beta')}</p>
        <Link
          href={whyHref}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mt-3"
        >
          {t('landing.home_cta.philosophy_link')} →
        </Link>
      </div>

      <div className="cosmos-planet" aria-hidden="true">
        <div className="cosmos-globe">
          <i className="cosmos-cloud c1" />
          <i className="cosmos-cloud c2" />
          <i className="cosmos-cloud c3" />
        </div>
      </div>
    </section>
  );
}
