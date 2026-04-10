'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { CATEGORY_BADGE } from './BlogPreviewSection';
import type { BlogArticle } from '@/data/blog-articles';
import type { Language } from '@/i18n/settings';

interface ShuffledBlogGridProps {
  pinned: BlogArticle[];
  pool: BlogArticle[];
  displayCount: number;
  translations: Record<
    string,
    { title: string; excerpt: string; category: string; readTime: string }
  >;
  lng: string;
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
                  <Image
                    src={`/articles/${article.slug}.png`}
                    alt={t.title}
                    fill
                    sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                    className="object-cover group-hover:scale-[1.03] transition-transform duration-300"
                  />
                </div>
                <CardHeader className="space-y-2 pt-4 pb-5">
                  <div className="flex items-center justify-between">
                    <span
                      className={cn(
                        'text-[10px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full',
                        CATEGORY_BADGE[article.category],
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
