import { type Metadata } from 'next';
import Link from 'next/link';
import Image from 'next/image';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { ThemeToggle } from '@/components/theme-toggle';
import { LanguageSelector } from '@/components/LanguageSelector';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { HowContent } from '@/components/guides/HowContent';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

interface HowPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: HowPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('how.meta.title');
  const description = t('how.meta.description');
  const canonicalUrl = buildLangUrl('/how', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/how', l);
  }
  langAlternates['x-default'] = buildLangUrl('/how', fallbackLng);

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
      images: [{ url: `${BASE_URL}/Title.png`, width: 2125, height: 1193, alt: title }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [`${BASE_URL}/Title.png`],
    },
  };
}

export default async function HowPage({ params }: HowPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const homePath = buildLocalizedPath('/', lng);
  const loginPath = buildLocalizedPath('/login', lng);
  const registerPath = buildLocalizedPath('/register', lng);

  return (
    <>
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: t('how.breadcrumb'), url: buildLangUrl('/how', lng) },
        ]}
      />

      <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        {/* Header */}
        <header className="border-b border-border/40 bg-background/80 backdrop-blur-xl sticky top-0 z-50">
          <div className="max-w-7xl mx-auto flex items-center justify-between px-4 sm:px-6 lg:px-8 py-3">
            <Link href={homePath} className="flex items-center gap-2 font-bold text-lg">
              <Image
                src="/v4-lia-brain.svg"
                alt="LIA"
                width={28}
                height={28}
                className="rounded-md"
              />
              <span>LIA</span>
            </Link>
            <div className="flex items-center gap-2">
              <LanguageSelector currentLocale={lng} />
              <ThemeToggle />
              <Link
                href={loginPath}
                className="hidden sm:inline-flex text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-3 py-2"
              >
                {t('landing.nav.login')}
              </Link>
              <Link
                href={registerPath}
                className="text-sm font-medium px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                {t('landing.nav.get_started')}
              </Link>
            </div>
          </div>
        </header>

        <main className="px-4 sm:px-6 lg:px-8 py-12">
          {/* Hero */}
          <div className="max-w-3xl mx-auto mb-12 text-center">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
              {t('how.hero.title')}
            </h1>
            <p className="text-lg text-muted-foreground leading-relaxed">
              {t('how.hero.subtitle')}
            </p>
          </div>

          {/* Content */}
          <HowContent lng={lng} />
        </main>

        {/* Footer */}
        <footer className="border-t border-border/40 py-6 mt-8">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-sm text-muted-foreground">
            {t('landing.footer.copyright', { year: new Date().getFullYear() })}
          </div>
        </footer>
      </div>
    </>
  );
}
