'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { FileText } from 'lucide-react';
import { ArticleIllustration } from '@/components/blog/ArticleIllustration';
import { LANDING_CARD_SIZES } from '@/lib/blog/article-images';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { BlogArticle, BlogCategory } from '@/data/blog-articles';
import type { Language } from '@/i18n/settings';

const CATEGORY_BADGE: Record<BlogCategory, string> = {
  architecture: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  integrations: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  features: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  security: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  technical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
};

interface ShuffledBlogGridProps {
  pinned: BlogArticle[];
  pool: BlogArticle[];
  displayCount: number;
  translations: Record<
    string,
    { title: string; excerpt: string; category: string; readTime: string }
  >;
  lng: string;
  /** Build-visible illustrations; an unillustrated article still keeps its card. */
  illustratedSlugs?: readonly string[];
}

/**
 * Client component that shuffles the non-pinned articles on mount,
 * keeping pinned articles in their fixed first positions.
 */
export function ShuffledBlogGrid({
  pinned,
  pool,
  displayCount,
  translations,
  lng,
  illustratedSlugs,
}: ShuffledBlogGridProps) {
  const [articles, setArticles] = useState<BlogArticle[]>(() => [
    ...pinned,
    ...pool.slice(0, displayCount - pinned.length),
  ]);

  useEffect(() => {
    const shuffled = [...pool];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    setArticles([...pinned, ...shuffled.slice(0, displayCount - pinned.length)]);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
      {articles.map((article, i) => {
        const articlePath = buildLocalizedPath(`/blog/${article.slug}`, lng as Language);
        const t = translations[article.slug];
        if (!t) return null;
        return (
          <FadeInOnScroll key={article.slug} delay={i * 80}>
            <Link href={articlePath} className="block group h-full">
              <Card className="hover-lift hover-glow h-full border-border/60 overflow-hidden transition-all">
                <div className="relative w-full aspect-[16/9] overflow-hidden">
                  {!illustratedSlugs || illustratedSlugs.includes(article.slug) ? (
                    <ArticleIllustration
                      slug={article.slug}
                      alt={t.title}
                      sizes={LANDING_CARD_SIZES}
                      className="group-hover:scale-[1.03] transition-transform duration-300"
                    />
                  ) : (
                    <div
                      aria-hidden="true"
                      className="grid size-full place-items-center bg-gradient-to-br from-primary/15 via-primary/5 to-background"
                    >
                      <FileText className="size-14 text-primary" />
                    </div>
                  )}
                </div>
                <CardHeader className="space-y-2 pt-4 pb-5">
                  <div className="flex items-center justify-between">
                    <span
                      className={cn(
                        'text-px-10 font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full',
                        CATEGORY_BADGE[article.category]
                      )}
                    >
                      {t.category}
                    </span>
                    <span className="text-xs text-muted-foreground">{t.readTime}</span>
                  </div>
                  <CardTitle className="text-sm leading-snug group-hover:text-primary transition-colors line-clamp-2">
                    {t.title}
                  </CardTitle>
                  <CardDescription className="text-xs leading-relaxed line-clamp-2">
                    {t.excerpt}
                  </CardDescription>
                </CardHeader>
              </Card>
            </Link>
          </FadeInOnScroll>
        );
      })}
    </div>
  );
}
