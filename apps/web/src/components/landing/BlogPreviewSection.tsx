import Link from 'next/link';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { ArrowRight } from 'lucide-react';
import { initI18next } from '@/i18n';
import { FadeInOnScroll } from './FadeInOnScroll';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES, type BlogArticle } from '@/data/blog-articles';
import { ShuffledBlogGrid } from './ShuffledBlogGrid';
import { ARTICLE_IMAGE_DEFAULT_WIDTH, articleImageSrc } from '@/lib/blog/article-images';

interface BlogPreviewSectionProps {
  lng: string;
}

/** Always-shown articles in fixed first positions */
const PINNED_SLUGS = ['react-execution-mode', 'multi-agent-orchestration'];

/** Total articles to display */
const DISPLAY_COUNT = 6;

export async function BlogPreviewSection({ lng }: BlogPreviewSectionProps) {
  const { t } = await initI18next(lng);
  const blogPath = buildLocalizedPath('/blog', lng as Language);

  const pinned = PINNED_SLUGS.map(slug => BLOG_ARTICLES.find(a => a.slug === slug)).filter(
    (a): a is BlogArticle => a !== undefined
  );

  const pool = BLOG_ARTICLES.filter(a => !PINNED_SLUGS.includes(a.slug));
  const illustratedSlugs = BLOG_ARTICLES.filter(article =>
    existsSync(
      join(process.cwd(), 'public', articleImageSrc(article.slug, ARTICLE_IMAGE_DEFAULT_WIDTH))
    )
  ).map(article => article.slug);

  const translations: Record<
    string,
    { title: string; excerpt: string; category: string; readTime: string }
  > = {};
  for (const article of BLOG_ARTICLES) {
    translations[article.slug] = {
      title: t(`blog.articles.${article.slug}.title`),
      excerpt: t(`blog.articles.${article.slug}.excerpt`),
      category: t(`blog.categories.${article.category}`),
      readTime: t('blog.read_time', { minutes: article.readTime }),
    };
  }

  return (
    <section
      id="blog"
      className="landing-section py-20 sm:py-24 bg-gradient-to-b from-muted/30 to-background"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-12">
            <h2 className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4">
              {t('landing.blog_preview.title')}
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              {t('landing.blog_preview.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        <ShuffledBlogGrid
          pinned={pinned}
          pool={pool}
          displayCount={DISPLAY_COUNT}
          translations={translations}
          lng={lng}
          illustratedSlugs={illustratedSlugs}
        />

        <FadeInOnScroll>
          <div className="text-center">
            <Link
              href={blogPath}
              className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:text-primary/90 transition-colors group"
            >
              {t('landing.blog_preview.view_all')}
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <span className="mx-3 text-muted-foreground">·</span>
            <Link
              href={buildLocalizedPath('/faq', lng as Language)}
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {t('landing.blog_preview.faq_link')}
            </Link>
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
