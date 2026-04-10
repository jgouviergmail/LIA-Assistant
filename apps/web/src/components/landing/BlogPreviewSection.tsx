import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { initI18next } from '@/i18n';
import { FadeInOnScroll } from './FadeInOnScroll';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES, type BlogArticle, type BlogCategory } from '@/data/blog-articles';
import { ShuffledBlogGrid } from './ShuffledBlogGrid';

interface BlogPreviewSectionProps {
  lng: string;
}

export const CATEGORY_BADGE: Record<BlogCategory, string> = {
  architecture: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  integrations: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  features: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  security: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  technical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
};

/** Always-shown articles in fixed first positions */
const PINNED_SLUGS = ['react-execution-mode', 'multi-agent-orchestration'];

/** Total articles to display */
const DISPLAY_COUNT = 6;

export async function BlogPreviewSection({ lng }: BlogPreviewSectionProps) {
  const { t } = await initI18next(lng);
  const blogPath = buildLocalizedPath('/blog', lng as Language);

  const pinned = PINNED_SLUGS.map((slug) => BLOG_ARTICLES.find((a) => a.slug === slug)).filter(
    (a): a is BlogArticle => a !== undefined,
  );

  const pool = BLOG_ARTICLES.filter((a) => !PINNED_SLUGS.includes(a.slug));

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
        />

        <FadeInOnScroll>
          <div className="text-center">
            <Link
              href={blogPath}
              className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:text-primary/80 transition-colors group"
            >
              {t('landing.blog_preview.view_all')}
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <span className="mx-3 text-muted-foreground/40">·</span>
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
