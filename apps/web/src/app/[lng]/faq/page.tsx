import { type Metadata } from 'next';
import Link from 'next/link';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { FAQPageJsonLd, BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { PublicFooter } from '@/components/layout/PublicFooter';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

/**
 * Public FAQ sections to display (subset of the full FAQ).
 * These are the most relevant questions for visitors who are not logged in.
 */
const PUBLIC_FAQ_SECTIONS = ['getting_started', 'privacy'] as const;

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

  // Collect all FAQ questions for JSON-LD schema
  const allQuestions: Array<{ question: string; answer: string }> = [];

  const sections = PUBLIC_FAQ_SECTIONS.map(section => {
    const count = parseInt(t(`faq.sections.${section}.count`));
    const questions = Array.from({ length: count }, (_, i) => {
      const q = t(`faq.sections.${section}.questions.q${i + 1}.question`);
      const a = t(`faq.sections.${section}.questions.q${i + 1}.answer`);
      allQuestions.push({ question: q, answer: a });
      return { question: q, answer: a };
    });

    return {
      key: section,
      title: t(`faq.sections.${section}.title`),
      description: t(`faq.sections.${section}.description`),
      questions,
    };
  });

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

      <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* Content — pt-16 offsets the fixed header height (h-16 = 64 px) */}
        <main className="max-w-4xl mx-auto px-4 sm:px-6 pt-24 pb-12">
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold tracking-tight mb-3">{t('faq.title')}</h1>
            <p className="text-lg text-muted-foreground">{t('faq.subtitle')}</p>
          </div>

          <div className="space-y-10">
            {sections.map(section => (
              <section key={section.key} className="space-y-4">
                <div className="mb-6">
                  <h2 className="text-2xl font-semibold">{section.title}</h2>
                  <p className="text-sm text-muted-foreground mt-1">{section.description}</p>
                </div>

                <div className="space-y-4">
                  {section.questions.map((item, idx) => (
                    <details
                      key={idx}
                      className="group rounded-lg border border-border/60 bg-card overflow-hidden"
                    >
                      <summary className="flex items-center justify-between cursor-pointer px-6 py-4 text-left font-medium hover:bg-muted/50 transition-colors">
                        <span>{item.question}</span>
                        <svg
                          className="h-5 w-5 text-muted-foreground shrink-0 ml-2 transition-transform group-open:rotate-180"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </summary>
                      <div className="px-6 pb-5 text-muted-foreground leading-relaxed border-t border-border/40 pt-4">
                        <div dangerouslySetInnerHTML={{ __html: item.answer }} />
                      </div>
                    </details>
                  ))}
                </div>
              </section>
            ))}
          </div>

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
