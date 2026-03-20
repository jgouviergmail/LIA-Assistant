import Link from 'next/link';
import Image from 'next/image';
import { ArrowRight } from 'lucide-react';
import { initI18next } from '@/i18n';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';
import { BLOG_ARTICLES, type BlogCategory } from '@/data/blog-articles';

interface BlogPreviewSectionProps {
  lng: string;
}

const CATEGORY_BADGE: Record<BlogCategory, string> = {
  architecture: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  integrations: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  features: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  security: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  technical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
};

/** Pick 6 articles: 1 per category + 1 extra from features (the largest category) */
const FEATURED_SLUGS = [
  'multi-agent-orchestration',
  'google-workspace',
  'voice-mode',
  'security-architecture',
  'observability',
  'human-in-the-loop',
];

export async function BlogPreviewSection({ lng }: BlogPreviewSectionProps) {
  const { t } = await initI18next(lng);
  const blogPath = buildLocalizedPath('/blog', lng as Language);

  const featured = FEATURED_SLUGS
    .map(slug => BLOG_ARTICLES.find(a => a.slug === slug))
    .filter(Boolean);

  return (
    <section id="blog" className="landing-section py-20 sm:py-24 bg-gradient-to-b from-muted/30 to-background">
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

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
          {featured.map((article, i) => {
            if (!article) return null;
            const articlePath = buildLocalizedPath(`/blog/${article.slug}`, lng as Language);
            return (
              <FadeInOnScroll key={article.slug} delay={i * 80}>
                <Link href={articlePath} className="block group h-full">
                  <Card className="hover-lift hover-glow h-full border-border/60 overflow-hidden transition-all">
                    <div className="relative w-full aspect-[16/9] overflow-hidden">
                      <Image
                        src={`/articles/${article.slug}.png`}
                        alt={t(`blog.articles.${article.slug}.title`)}
                        fill
                        sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                        className="object-cover group-hover:scale-[1.03] transition-transform duration-300"
                      />
                    </div>
                    <CardHeader className="space-y-2 pt-4 pb-5">
                      <div className="flex items-center justify-between">
                        <span className={cn('text-[10px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full', CATEGORY_BADGE[article.category])}>
                          {t(`blog.categories.${article.category}`)}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {t('blog.read_time', { minutes: article.readTime })}
                        </span>
                      </div>
                      <CardTitle className="text-sm leading-snug group-hover:text-primary transition-colors line-clamp-2">
                        {t(`blog.articles.${article.slug}.title`)}
                      </CardTitle>
                      <CardDescription className="text-xs leading-relaxed line-clamp-2">
                        {t(`blog.articles.${article.slug}.excerpt`)}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </Link>
              </FadeInOnScroll>
            );
          })}
        </div>

        <FadeInOnScroll>
          <div className="text-center">
            <Link
              href={blogPath}
              className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:text-primary/80 transition-colors group"
            >
              {t('landing.blog_preview.view_all')}
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
