import { type Metadata } from 'next';
import Link from 'next/link';

import { ChangelogHistory } from '@/components/changelog/ChangelogHistory';
import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { PublicFooter } from '@/components/layout/PublicFooter';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { initI18next, validateLanguage } from '@/i18n';
import { fallbackLng, languages, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';

/**
 * `/changelog` — the release history, with a URL of its own.
 *
 * A reading page like `/faq` or `/why`: same cosmos CALM scope, same header
 * and footer. It exists because "see the full history" needs somewhere honest
 * to point — the public FAQ never carried a changelog, so the promise led to
 * a page without it. Giving history a canonical, hreflang-ed, sitemapped URL
 * also makes it linkable and indexable, which an in-page anchor never was.
 *
 * It reuses the changelog's own translations (`faq.changelog.*`) rather than
 * inventing a second title for the same thing: one history, one wording, six
 * locales already written.
 */

function buildLangUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

interface ChangelogPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: ChangelogPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = `${t('faq.changelog.title')} — ${t('landing.meta.title')}`;
  const description = t('faq.changelog.description');
  const canonicalUrl = buildLangUrl('/changelog', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/changelog', l);
  }
  langAlternates['x-default'] = buildLangUrl('/changelog', fallbackLng);

  return {
    title,
    description,
    alternates: {
      canonical: canonicalUrl,
      languages: langAlternates,
    },
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      locale: LOCALE_MAP[lng],
      alternateLocale: languages.filter(l => l !== lng).map(l => LOCALE_MAP[l]),
      type: 'website',
    },
    twitter: {
      title,
      description,
    },
  };
}

export default async function ChangelogPage({ params }: ChangelogPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const registerPath = lng === fallbackLng ? '/register' : `/${lng}/register`;

  return (
    <>
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: t('faq.changelog.title'), url: buildLangUrl('/changelog', lng) },
        ]}
      />

      <div className="landing-page cosmos cosmos-calm min-h-screen">
        <CosmosDarkFirst />
        <CosmicBackdrop />
        <CosmosThemeDefault />
        <LandingHeader lng={lng} />

        {/* pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="max-w-4xl mx-auto px-4 sm:px-6 pt-24 pb-12">
          <div className="text-center mb-10">
            {/* Bare h1 + iconised section headings: the exact shape every
                public reading page uses (`/faq`, `/more`, `/story`). */}
            <h1 className="mb-3 text-4xl font-bold tracking-tight">{t('faq.changelog.title')}</h1>
            <p className="text-lg text-muted-foreground">{t('faq.changelog.description')}</p>
          </div>

          <ChangelogHistory lng={lng} />

          {/* CTA */}
          <div className="mt-16 text-center rounded-2xl bg-primary/5 border border-primary/20 p-8">
            <h2 className="text-2xl font-semibold mb-3">{t('landing.cta.title')}</h2>
            <p className="text-muted-foreground mb-6">{t('landing.cta.subtitle')}</p>
            <Link
              href={registerPath}
              className="inline-flex items-center px-6 py-3 rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors"
            >
              {t('landing.cta.button')}
            </Link>
          </div>
        </main>

        <PublicFooter lng={lng} />
      </div>
    </>
  );
}
