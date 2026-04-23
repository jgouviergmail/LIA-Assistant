import { type Metadata } from 'next';
import { notFound } from 'next/navigation';
import { initI18next, validateLanguage } from '@/i18n';
import { languages, fallbackLng, LOCALE_MAP } from '@/i18n/settings';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES, getArticleBySlug, getAdjacentArticles } from '@/data/blog-articles';
import { BlogArticleContent } from '@/components/blog/BlogArticleContent';
import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { PublicFooter } from '@/components/layout/PublicFooter';

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://lia.jeyswork.com';

function buildLangUrl(path: string, lng: Language): string {
  return lng === fallbackLng ? `${BASE_URL}${path}` : `${BASE_URL}/${lng}${path}`;
}

interface ArticlePageProps {
  params: Promise<{ lng: string; slug: string }>;
}

export async function generateStaticParams() {
  const params: { lng: string; slug: string }[] = [];
  for (const lng of languages) {
    for (const article of BLOG_ARTICLES) {
      params.push({ lng, slug: article.slug });
    }
  }
  return params;
}

export async function generateMetadata({ params }: ArticlePageProps): Promise<Metadata> {
  const { lng: lngParam, slug } = await params;
  const lng = validateLanguage(lngParam);
  const article = getArticleBySlug(slug);
  if (!article) return {};

  const { t } = await initI18next(lng);
  const title = t(`blog.articles.${slug}.title`);
  const description = t(`blog.articles.${slug}.excerpt`);
  const canonicalUrl = buildLangUrl(`/blog/${slug}`, lng);

  const langAlternates: Record<string, string> = {};
  for (const l of languages) {
    langAlternates[l] = buildLangUrl(`/blog/${slug}`, l);
  }
  langAlternates['x-default'] = buildLangUrl(`/blog/${slug}`, fallbackLng);

  const imageUrl = `${BASE_URL}/articles/${slug}.png`;

  return {
    title: `${title} — LIA Blog`,
    description,
    keywords: article.tags,
    authors: [{ name: 'LIA', url: BASE_URL }],
    alternates: {
      canonical: canonicalUrl,
      languages: langAlternates,
    },
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      type: 'article',
      locale: LOCALE_MAP[lng],
      alternateLocale: languages.filter(l => l !== lng).map(l => LOCALE_MAP[l]),
      publishedTime: article.date,
      section: article.category,
      tags: article.tags,
      images: [{ url: imageUrl, width: 1200, height: 675, alt: title }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [imageUrl],
    },
  };
}

export default async function BlogArticlePage({ params }: ArticlePageProps) {
  const { lng: lngParam, slug } = await params;
  const lng = validateLanguage(lngParam);
  const article = getArticleBySlug(slug);
  if (!article) notFound();

  const { t } = await initI18next(lng);
  const { prev, next } = getAdjacentArticles(slug);

  const localeMap: Record<string, string> = {
    fr: 'fr-FR',
    en: 'en-US',
    de: 'de-DE',
    es: 'es-ES',
    it: 'it-IT',
    zh: 'zh-CN',
  };

  // Build JSON-LD for BlogPosting
  const articleImageUrl = `${BASE_URL}/articles/${slug}.png`;
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BlogPosting',
    headline: t(`blog.articles.${slug}.title`),
    description: t(`blog.articles.${slug}.excerpt`),
    image: articleImageUrl,
    datePublished: article.date,
    dateModified: article.date,
    author: {
      '@type': 'Organization',
      name: 'LIA',
      url: BASE_URL,
    },
    publisher: {
      '@type': 'Organization',
      name: 'LIA',
      logo: { '@type': 'ImageObject', url: `${BASE_URL}/icon.svg` },
    },
    mainEntityOfPage: buildLangUrl(`/blog/${slug}`, lng),
    keywords: article.tags.join(', '),
    inLanguage: localeMap[lng] || 'fr-FR',
    wordCount: article.readTime * 200,
    articleSection: article.category,
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <BreadcrumbJsonLd
        items={[
          { name: 'LIA', url: buildLangUrl('/', lng) },
          { name: 'Blog', url: buildLangUrl('/blog', lng) },
          { name: t(`blog.articles.${slug}.title`), url: buildLangUrl(`/blog/${slug}`, lng) },
        ]}
      />

      <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        {/* Header — same as landing page (fixed top, transparent until scroll) */}
        <LandingHeader lng={lng} />

        {/* pt-24 offsets the fixed header height (h-16 = 64 px) */}
        <main className="px-4 sm:px-6 lg:px-8 pt-24 pb-12">
          <BlogArticleContent
            article={article}
            title={t(`blog.articles.${slug}.title`)}
            body={t(`blog.articles.${slug}.body`)}
            categoryLabel={t(`blog.categories.${article.category}`)}
            readTimeLabel={t('blog.read_time', { minutes: article.readTime })}
            backLabel={t('blog.back_to_list')}
            prev={prev ? { slug: prev.slug, title: t(`blog.articles.${prev.slug}.title`) } : null}
            next={next ? { slug: next.slug, title: t(`blog.articles.${next.slug}.title`) } : null}
            lng={lng}
          />
        </main>

        <PublicFooter lng={lng} />
      </div>
    </>
  );
}
