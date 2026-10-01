import { cn } from '@/lib/utils';
import {
  ARTICLE_IMAGE_DEFAULT_WIDTH,
  articleImageSrc,
  articleImageSrcSet,
} from '@/lib/blog/article-images';

interface ArticleIllustrationProps {
  slug: string;
  alt: string;
  /** The `sizes` of the surface drawing it — one of the constants in `article-images.ts`. */
  sizes: string;
  /** Above the fold: load eagerly and first (the article hero, the first cards). */
  priority?: boolean;
  className?: string;
}

/**
 * An article's illustration, served as pre-generated static variants.
 *
 * A plain `<img>` on purpose (ADR-330): the candidates already exist as files,
 * so `next/image` would only add a resize on the host and a response the CDN
 * cannot cache. The caller sizes the frame; the image fills it.
 */
export function ArticleIllustration({
  slug,
  alt,
  sizes,
  priority = false,
  className,
}: ArticleIllustrationProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- pre-generated static variants, no optimizer (ADR-330)
    <img
      src={articleImageSrc(slug, ARTICLE_IMAGE_DEFAULT_WIDTH)}
      srcSet={articleImageSrcSet(slug)}
      sizes={sizes}
      alt={alt}
      loading={priority ? 'eager' : 'lazy'}
      decoding="async"
      fetchPriority={priority ? 'high' : undefined}
      className={cn('size-full object-cover', className)}
    />
  );
}
