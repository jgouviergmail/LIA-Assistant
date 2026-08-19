/**
 * "What just shipped" — the last few releases, on the landing page.
 *
 * A visitor decides whether a product is alive by whether it moves, and until
 * now the only proof was four clicks deep in the FAQ, behind a fold. This
 * section puts the three most recent releases where someone who has not signed
 * up yet will actually meet them, and hands the full history to `/changelog`
 * — it teases, it does not duplicate. It used to hand it to `/faq`, where the
 * public FAQ carries no changelog at all: the promise led to a page without
 * it (`__tests__/ChangelogSection.test.tsx` now pins this button's
 * destination; `components/__tests__/changelog-destination.test.tsx` pins the
 * same promise in both footers).
 *
 * A SERVER component, like every other band of this page (`TechSection`,
 * `UseCasesSection`, `BlogPreviewSection`): the content is static editorial
 * text, so it costs no client bundle and — the reason that matters — release
 * notes rendered on the server are indexable.
 *
 * It reads the SAME list as every other changelog surface
 * (`lib/changelog.ts`), so a release cannot appear here and be missing there;
 * "newest first" is that list's order, never a hand-picked selection that
 * would freeze the day somebody forgot to update it.
 *
 * The bullets themselves come from the shared `ChangelogItems`, so the rule
 * "an unusable count renders NO bullet" has one implementation across the three
 * surfaces that quote a release.
 */

import Link from 'next/link';
import { ArrowRight, Sparkles } from 'lucide-react';

import { ChangelogItems } from '@/components/changelog/ChangelogItems';
import { initI18next } from '@/i18n';
import {
  LANDING_CHANGELOG_COUNT,
  changelogDateKey,
  changelogTitleKey,
  latestChangelogVersions,
} from '@/lib/changelog';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

import { FadeInOnScroll } from './FadeInOnScroll';

export async function ChangelogSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);
  const versions = latestChangelogVersions(LANDING_CHANGELOG_COUNT);

  return (
    <section
      id="changelog"
      aria-labelledby="changelog-title"
      className="landing-section bg-card py-20"
    >
      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="mb-12 text-center">
            <p className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-primary">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              {t('landing.changelog.eyebrow')}
            </p>
            <h2
              id="changelog-title"
              className="mb-4 text-3xl font-bold tracking-tight mobile:text-4xl"
            >
              {t('landing.changelog.title')}
            </h2>
            <p className="mx-auto max-w-2xl text-lg text-muted-foreground">
              {t('landing.changelog.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        <ol className="space-y-4">
          {versions.map((version, index) => (
            <li key={version}>
              <FadeInOnScroll delay={index * 80}>
                <article className="rounded-2xl border border-border bg-background p-6">
                  <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h3 className="text-lg font-semibold tracking-tight">
                      {t(changelogTitleKey(version))}
                    </h3>
                    <p className="text-xs text-muted-foreground">{t(changelogDateKey(version))}</p>
                  </header>
                  <ChangelogItems version={version} t={t} className="mt-4 space-y-2.5" />
                </article>
              </FadeInOnScroll>
            </li>
          ))}
        </ol>

        <div className="mt-8 text-center">
          <Link
            href={buildLocalizedPath('/changelog', lng as Language)}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-medium transition-colors hover:border-primary/60 hover:bg-accent/40"
          >
            {t('landing.changelog.all')}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  );
}
