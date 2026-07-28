import { type Metadata } from 'next';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { InteractiveChatMockup } from '@/components/landing/InteractiveChatMockup';

/**
 * Standalone URL for the hero conversation animation, made to be shared on
 * social networks and embedded in publications: no header, no footer, no auth
 * redirect — the four-act mockup on the hero's ambient background, made
 * INTERACTIVE here (UX P12): scene pastilles, pause/replay, progress and a
 * closing CTA. The auto loop is preserved until the visitor interacts.
 * Localized like every route (the mockup aria text doubles as the page
 * description).
 */

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

interface DemoPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: DemoPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('landing.meta.title');
  const description = t('landing.chat_mockup.aria');
  const canonicalUrl = buildLangUrl('/demo', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/demo', l);
  }
  langAlternates['x-default'] = buildLangUrl('/demo', fallbackLng);

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
      images: [{ url: '/Title.png', width: 2125, height: 1193, alt: title }],
    },
    twitter: {
      title,
      description,
      images: ['/Title.png'],
    },
  };
}

export default async function DemoPage({ params }: DemoPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      {/* Same ambient background as the landing hero */}
      <div className="absolute inset-0 -z-10" aria-hidden="true">
        <div className="absolute -top-32 -left-32 w-[36rem] h-[36rem] rounded-full bg-primary/15 blur-3xl" />
        <div className="absolute top-1/3 -right-40 w-[32rem] h-[32rem] rounded-full bg-violet-500/10 blur-3xl" />
        <div className="absolute bottom-0 left-1/4 w-[28rem] h-[20rem] rounded-full bg-cyan-500/10 blur-3xl" />
      </div>

      <div className="w-full max-w-md">
        <InteractiveChatMockup lng={lng} />
      </div>
    </main>
  );
}
