/**
 * Blog illustrations as pre-generated static variants (ADR-330).
 *
 * Every article has one master illustration, from which
 * `apps/web/scripts/build-article-images.mjs` writes four WebP widths and a
 * 1200×675 JPEG for the social cards. Nothing is resized at request time: the
 * image optimizer decoded a 7-MB RGBA PNG per variant per cache expiry on the
 * production host, and its `/_next/image` responses carry no extension, so the
 * CDN never cached them (measured 2026-10-01: 0.4-0.6 s per cold variant,
 * 4.8 s when a page's cards arrived together). Static files are cached by
 * extension at the edge and cost the host nothing.
 *
 * This module is the ONE place that spells the file names and the `sizes`
 * each surface needs; the generator, the cards, the hero and the metadata
 * all read it.
 */

/** Widths written for every article, smallest first (device pixels). */
export const ARTICLE_IMAGE_WIDTHS = [480, 768, 1024, 1536] as const;

export type ArticleImageWidth = (typeof ARTICLE_IMAGE_WIDTHS)[number];

/** The intrinsic size the `<img>` claims before any candidate is chosen. */
export const ARTICLE_IMAGE_DEFAULT_WIDTH: ArticleImageWidth = 1024;

/** The social image (og:image / twitter:image / JSON-LD): a 16:9 JPEG. */
export const ARTICLE_SOCIAL_IMAGE = { width: 1200, height: 675 } as const;

/**
 * Blog index cards: 1 / 2 / 3 / 4 columns at 640 / 880 (`--breakpoint-mobile`)
 * / 1024 px, inside `max-w-7xl` — a card never exceeds ~300 CSS px there.
 */
export const ARTICLE_CARD_SIZES =
  '(max-width: 640px) 100vw, (max-width: 880px) 50vw, (max-width: 1024px) 33vw, 300px';

/** Landing preview grid: 1 / 2 / 3 columns at 640 / 1024 px, same cap. */
export const LANDING_CARD_SIZES = '(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 390px';

/** The article page hero fills the prose column (`max-w-3xl`). */
export const ARTICLE_HERO_SIZES = '(max-width: 768px) 100vw, 768px';

/** Public path of one WebP variant. */
export function articleImageSrc(slug: string, width: ArticleImageWidth): string {
  return `/articles/${slug}-${width}.webp`;
}

/** The `srcset` listing every variant with its width descriptor. */
export function articleImageSrcSet(slug: string): string {
  return ARTICLE_IMAGE_WIDTHS.map(width => `${articleImageSrc(slug, width)} ${width}w`).join(', ');
}

/** Public path of the social image. */
export function articleSocialImageSrc(slug: string): string {
  return `/articles/${slug}-og.jpg`;
}
