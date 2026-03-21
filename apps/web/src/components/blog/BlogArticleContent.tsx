import Link from 'next/link';
import Image from 'next/image';
import { ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { BlogArticle, BlogCategory } from '@/data/blog-articles';

const CATEGORY_STYLES: Record<BlogCategory, string> = {
  architecture: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  integrations: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  features: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  security: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  technical: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
};

interface BlogArticleContentProps {
  article: BlogArticle;
  title: string;
  body: string;
  categoryLabel: string;
  readTimeLabel: string;
  backLabel: string;
  prev?: { slug: string; title: string } | null;
  next?: { slug: string; title: string } | null;
  lng: string;
}

function buildBlogPath(slug: string, lng: string): string {
  return lng === 'fr' ? `/blog/${slug}` : `/${lng}/blog/${slug}`;
}

export function BlogArticleContent({
  article,
  title,
  body,
  categoryLabel,
  readTimeLabel,
  backLabel,
  prev,
  next,
  lng,
}: BlogArticleContentProps) {
  const badgeClass = CATEGORY_STYLES[article.category];
  const blogListPath = lng === 'fr' ? '/blog' : `/${lng}/blog`;

  return (
    <article className="relative max-w-3xl mx-auto">
      {/* Back link */}
      <Link
        href={blogListPath}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6 group"
      >
        <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
        {backLabel}
      </Link>

      {/* Hero illustration */}
      <div className="relative w-full aspect-[16/9] rounded-xl overflow-hidden mb-8">
        <Image
          src={`/articles/${article.slug}.png`}
          alt={title}
          fill
          sizes="(max-width: 768px) 100vw, 768px"
          className="object-cover"
          priority
        />
      </div>

      {/* Compact header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <span
            className={cn(
              'text-xs font-semibold uppercase tracking-wider px-3 py-1 rounded-full',
              badgeClass
            )}
          >
            {categoryLabel}
          </span>
          <span className="text-xs text-muted-foreground">{readTimeLabel}</span>
        </div>

        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight leading-tight text-foreground">
          {title}
        </h1>
      </header>

      {/* Separator */}
      <div className="h-px bg-border/50 mb-8" />

      {/* Article body */}
      <div
        className="blog-article-body prose dark:prose-invert max-w-none
          prose-headings:font-semibold prose-headings:tracking-tight prose-headings:text-foreground
          prose-h2:text-lg prose-h2:mt-8 prose-h2:mb-3
          prose-h3:text-base prose-h3:mt-6 prose-h3:mb-2
          prose-p:text-[0.938rem] prose-p:leading-relaxed prose-p:text-muted-foreground prose-p:mb-4
          prose-li:text-[0.938rem] prose-li:leading-relaxed prose-li:text-muted-foreground
          prose-ul:my-3 prose-ol:my-3
          prose-strong:text-foreground prose-strong:font-semibold
          prose-a:text-primary prose-a:font-medium prose-a:no-underline hover:prose-a:underline prose-a:underline-offset-4
          prose-code:text-sm prose-code:font-medium prose-code:text-primary prose-code:bg-primary/8 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:content-none prose-code:after:content-none
          prose-pre:bg-muted/50 prose-pre:border prose-pre:border-border/40 prose-pre:rounded-lg
          prose-blockquote:border-l-primary/40 prose-blockquote:bg-muted/20 prose-blockquote:rounded-r-lg prose-blockquote:py-0.5 prose-blockquote:not-italic
          prose-img:rounded-lg prose-img:shadow-md"
        dangerouslySetInnerHTML={{ __html: body }}
      />

      {/* Tags */}
      <div className="flex flex-wrap gap-2 mt-8 pt-6 border-t border-border/40">
        {article.tags.map(tag => (
          <span
            key={tag}
            className="text-xs font-medium px-3 py-1 rounded-full bg-muted/80 text-muted-foreground"
          >
            #{tag}
          </span>
        ))}
      </div>

      {/* Prev / Next navigation */}
      {(prev || next) && (
        <nav className="grid grid-cols-2 gap-4 mt-6 pt-6 border-t border-border/40">
          {prev ? (
            <Link
              href={buildBlogPath(prev.slug, lng)}
              className="group rounded-lg border border-border/50 p-4 hover:border-primary/30 hover:bg-primary/5 transition-all"
            >
              <span className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                <ChevronLeft className="w-3 h-3 transition-transform group-hover:-translate-x-0.5" />
                Previous
              </span>
              <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors line-clamp-2">
                {prev.title}
              </span>
            </Link>
          ) : (
            <div />
          )}
          {next ? (
            <Link
              href={buildBlogPath(next.slug, lng)}
              className="group rounded-lg border border-border/50 p-4 hover:border-primary/30 hover:bg-primary/5 transition-all text-right"
            >
              <span className="flex items-center justify-end gap-1 text-xs text-muted-foreground mb-1">
                Next
                <ChevronRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
              </span>
              <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors line-clamp-2">
                {next.title}
              </span>
            </Link>
          ) : (
            <div />
          )}
        </nav>
      )}
    </article>
  );
}
