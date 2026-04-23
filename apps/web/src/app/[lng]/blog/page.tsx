import { type Metadata } from 'next';
import Link from 'next/link';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES, BLOG_CATEGORIES } from '@/data/blog-articles';
import { BlogCard } from '@/components/blog/BlogCard';
import { BreadcrumbJsonLd, BlogListJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { PublicFooter } from '@/components/layout/PublicFooter';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

interface BlogPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: BlogPageProps): Promise<Metadata> {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const title = t('blog.meta.title');
  const description = t('blog.meta.description');
  const canonicalUrl = buildLangUrl('/blog', lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl('/blog', l);
  }
  langAlternates['x-default'] = buildLangUrl('/blog', fallbackLng);

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

export default async function BlogPage({ params }: BlogPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  const registerPath = buildLocalizedPath('/register', lng);
  const blogUrl = buildLangUrl('/blog', lng);
  const homeUrl = buildLangUrl('/', lng);

  return (
    <>
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: homeUrl },
          { name: 'Blog', url: blogUrl },
        ]}
      />
      <BlogListJsonLd
        lng={lng}
        title={t('blog.meta.title')}
        description={t('blog.meta.description')}
        articles={BLOG_ARTICLES.map(a => ({
          title: t(`blog.articles.${a.slug}.title`),
          url: buildLangUrl(`/blog/${a.slug}`, lng),
          date: a.date,
          excerpt: t(`blog.articles.${a.slug}.excerpt`),
        }))}
      />
      <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-12">
          {/* Hero */}
          <div className="text-center mb-12">
            <h1 className="text-4xl mobile:text-5xl font-bold tracking-tight mb-4">
              {t('blog.hero.title')}
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              {t('blog.hero.subtitle')}
            </p>
          </div>

          {/* Category sections */}
          {BLOG_CATEGORIES.map(category => {
            const articles = BLOG_ARTICLES.filter(a => a.category === category.id);
            if (articles.length === 0) return null;

            return (
              <section key={category.id} className="mb-16">
                <h2 className="text-2xl font-semibold tracking-tight mb-2">
                  {t(`blog.categories.${category.id}`)}
                </h2>
                <p className="text-sm text-muted-foreground mb-6">
                  {t(`blog.categories.${category.id}_desc`)}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 mobile:grid-cols-3 lg:grid-cols-4 gap-5">
                  {articles.map(article => (
                    <BlogCard
                      key={article.slug}
                      article={article}
                      title={t(`blog.articles.${article.slug}.title`)}
                      excerpt={t(`blog.articles.${article.slug}.excerpt`)}
                      categoryLabel={t(`blog.categories.${category.id}`)}
                      readTimeLabel={t('blog.read_time', { minutes: article.readTime })}
                      lng={lng}
                    />
                  ))}
                </div>
              </section>
            );
          })}

          {/* CTA */}
          <div className="mt-8 text-center rounded-2xl bg-primary/5 border border-primary/20 p-8">
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
