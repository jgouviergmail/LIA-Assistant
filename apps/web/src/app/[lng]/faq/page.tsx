import { type Metadata } from 'next';
import Link from 'next/link';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { FAQPageJsonLd, BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { PublicFooter } from '@/components/layout/PublicFooter';
import { PublicFAQContent } from '@/components/faq/PublicFAQContent';
import { PUBLIC_FAQ_SECTIONS } from '@/components/faq/faq-sections';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import { getSiteOrigin, localizedUrl } from '@/lib/site-origin';


function buildLangUrl(path: string, lng: Language): string {
  return localizedUrl(getSiteOrigin(), path, lng);
}

interface FAQPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: FAQPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = `FAQ — ${t('landing.meta.title')}`;
  const description = t('faq.subtitle');
  const canonicalUrl = buildLangUrl('/faq', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/faq', l);
  }
  langAlternates['x-default'] = buildLangUrl('/faq', fallbackLng);

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
    },
    twitter: {
      title,
      description,
    },
  };
}

export default async function PublicFAQPage({ params }: FAQPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  // Collect every public question for the FAQPage JSON-LD schema (the client
  // component renders the same translations interactively).
  const allQuestions: Array<{ question: string; answer: string }> = [];
  for (const section of PUBLIC_FAQ_SECTIONS) {
    const count = parseInt(t(`faq.sections.${section}.count`));
    for (let i = 1; i <= count; i++) {
      allQuestions.push({
        question: t(`faq.sections.${section}.questions.q${i}.question`),
        answer: t(`faq.sections.${section}.questions.q${i}.answer`),
      });
    }
  }

  const registerPath = lng === fallbackLng ? '/register' : `/${lng}/register`;

  return (
    <>
      <FAQPageJsonLd questions={allQuestions} />
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: 'FAQ', url: buildLangUrl('/faq', lng) },
        ]}
      />

      <div className="landing-page cosmos cosmos-calm min-h-screen">
        <CosmosDarkFirst />
        <CosmicBackdrop />
        <CosmosThemeDefault />
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* Content — pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="max-w-4xl mx-auto px-4 sm:px-6 pt-24 pb-12">
          <div className="text-center mb-10">
            <h1 className="text-4xl font-bold tracking-tight mb-3">{t('faq.title')}</h1>
            <p className="text-lg text-muted-foreground">{t('faq.subtitle')}</p>
          </div>

          <PublicFAQContent lng={lng} />

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
