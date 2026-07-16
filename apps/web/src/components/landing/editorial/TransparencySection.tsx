import Link from 'next/link';
import { initI18next } from '@/i18n';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { AUDIT_REPORT_URL } from '../constants';

/**
 * "She has nothing to hide." — the trust positioning no competitor can copy:
 * per-message cost shown as a brand motif, the public audit score, open
 * source, and the AI-written/human-directed story. Replaces the former
 * numbers section (engineering tiles moved to Under the hood) and absorbs
 * the REX banner. Ends on the mid-page CTA, placed at peak trust.
 */

const GITHUB_REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

export async function TransparencySection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  const storyHref = buildLocalizedPath('/story', lng as Language);
  const registerHref = buildLocalizedPath('/register', lng as Language);

  const proofs = [
    { key: 'p1', href: undefined },
    { key: 'p2', href: AUDIT_REPORT_URL },
    { key: 'p3', href: GITHUB_REPO_URL },
    { key: 'p4', href: storyHref },
  ] as const;

  return (
    <section
      id="transparency"
      aria-labelledby="transparency-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card py-24"
    >
      <div className="mx-auto max-w-6xl px-4 text-center sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <h2 id="transparency-title" className="text-3xl font-bold tracking-tight mobile:text-4xl">
            {t('landing.transparency.title')}
          </h2>
          <p className="mx-auto mt-3 max-w-[60ch] text-muted-foreground">
            {t('landing.transparency.sub')}
          </p>

          {/* The real per-message cost counter, elevated into a brand motif */}
          <p className="mx-auto mt-8 w-fit rounded-2xl border border-border bg-background px-6 py-3.5 text-base shadow-lg tabular-nums mobile:text-lg">
            {t('landing.transparency.cost_prefix')}{' '}
            <span className="text-orange-500">🟠 1 240 IN</span>{' '}
            <span className="text-green-600">🟢 210 OUT</span>{' '}
            <strong className="font-extrabold">· 0,003 €</strong>
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {t('landing.transparency.cost_note')}
          </p>
        </FadeInOnScroll>

        <div className="mt-10 grid gap-4 text-left sm:grid-cols-2 lg:grid-cols-4">
          {proofs.map(({ key, href }, i) => (
            <FadeInOnScroll key={key} delay={i * 80}>
              <div className="h-full rounded-2xl border border-border bg-background p-5 transition-colors hover:border-primary/30">
                <h3 className="text-[15px] font-bold tracking-tight">
                  {t(`landing.transparency.${key}_t`)}
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  {t(`landing.transparency.${key}_d`)}
                </p>
                {href &&
                  (href.startsWith('http') ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-3 inline-block text-xs font-medium text-primary hover:underline"
                    >
                      {t(`landing.transparency.${key}_link`)} →
                    </a>
                  ) : (
                    <Link
                      href={href}
                      className="mt-3 inline-block text-xs font-medium text-primary hover:underline"
                    >
                      {t(`landing.transparency.${key}_link`)} →
                    </Link>
                  ))}
              </div>
            </FadeInOnScroll>
          ))}
        </div>

        <FadeInOnScroll>
          <p className="mt-9 text-sm text-muted-foreground">{t('landing.transparency.honest')}</p>
          {/* Mid-page CTA at peak trust */}
          <Link
            href={registerHref}
            className="mt-5 inline-block rounded-xl bg-primary px-7 py-3 text-sm font-semibold text-primary-foreground transition-transform hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {t('landing.transparency.cta')}
          </Link>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
