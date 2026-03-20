import Link from 'next/link';
import Image from 'next/image';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { BlogArticle, BlogCategory } from '@/data/blog-articles';

const CATEGORY_BADGE: Record<BlogCategory, string> = {
  architecture: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  integrations: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  features: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  security: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  technical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
};

interface BlogCardProps {
  article: BlogArticle;
  title: string;
  excerpt: string;
  categoryLabel: string;
  readTimeLabel: string;
  lng: string;
}

export function BlogCard({ article, title, excerpt, categoryLabel, readTimeLabel, lng }: BlogCardProps) {
  const badgeClass = CATEGORY_BADGE[article.category];
  const blogPath = lng === 'fr' ? `/blog/${article.slug}` : `/${lng}/blog/${article.slug}`;

  return (
    <Link href={blogPath} className="block group">
      <Card className="hover-lift hover-glow h-full border-border/60 overflow-hidden transition-all">
        {/* Article illustration */}
        <div className="relative w-full aspect-[16/9] overflow-hidden">
          <Image
            src={`/articles/${article.slug}.png`}
            alt={title}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover group-hover:scale-[1.03] transition-transform duration-300"
          />
        </div>
        <CardHeader className="space-y-2.5 pt-4">
          <div className="flex items-center justify-between">
            <span className={cn('text-[10px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full', badgeClass)}>
              {categoryLabel}
            </span>
            <span className="text-xs text-muted-foreground">{readTimeLabel}</span>
          </div>
          <CardTitle className="text-base leading-snug group-hover:text-primary transition-colors line-clamp-2">
            {title}
          </CardTitle>
          <CardDescription className="text-xs leading-relaxed line-clamp-3">
            {excerpt}
          </CardDescription>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {article.tags.slice(0, 3).map(tag => (
              <span
                key={tag}
                className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </div>
        </CardHeader>
      </Card>
    </Link>
  );
}
