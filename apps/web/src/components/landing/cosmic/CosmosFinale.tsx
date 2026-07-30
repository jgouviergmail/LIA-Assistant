'use client';

/**
 * Cosmic finale: the real CTA content (exact `landing.cta.*` keys, register
 * link, LIA's last-word bubble) above a clean planet horizon (deep sphere,
 * drifting clouds).
 */

import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { GhostWord } from './GhostWord';

export function CosmosFinale({ lng }: { lng: string }) {
  const { t } = useTranslation();
  const registerHref = buildLocalizedPath('/register', lng as Language);
  const whyHref = buildLocalizedPath('/why', lng as Language);

  return (
    <section
      aria-labelledby="cosmos-cta-title"
      className="landing-section relative overflow-clip pt-24 text-center"
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
            {t('landing.cta.bubble')}
          </span>
        </div>
        <h2
          id="cosmos-cta-title"
          className="text-3xl mobile:text-4xl lg:text-5xl font-extrabold tracking-tight mb-6"
        >
          {t('landing.cta.title')}
        </h2>
        <p className="text-lg text-muted-foreground mb-8 max-w-xl mx-auto">
          {t('landing.cta.subtitle')}
        </p>
        <Button asChild size="lg" className="text-base px-10 font-semibold">
          <Link href={registerHref}>{t('landing.cta.button')}</Link>
        </Button>
        <p className="text-sm text-muted-foreground mt-6">{t('landing.cta.note_beta')}</p>
        <Link
          href={whyHref}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground/80 hover:text-foreground transition-colors mt-3"
        >
          {t('landing.cta.philosophy_link')} →
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
