/**
 * Every published article has its full set of pre-generated illustrations.
 *
 * The variants are files, not a runtime resize (ADR-330): a slug added to
 * `BLOG_ARTICLES` without running `scripts/build-article-images.mjs` would
 * ship four 404s and a broken social card, and nothing else would notice.
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { BLOG_ARTICLES } from '../blog-articles';
import {
  ARTICLE_IMAGE_WIDTHS,
  articleImageSrc,
  articleSocialImageSrc,
} from '@/lib/blog/article-images';

const PUBLIC_DIR = join(__dirname, '..', '..', '..', 'public');

/**
 * Articles published without a master illustration — shrink-only, each with
 * the reason it is still here. The guard found the first one on its first
 * run: `tabular-administration` shipped in v2.2.0 with no image at all (its
 * card and hero showed a broken image under next/image as well), and an
 * illustration is a decision for the owner, not for a test.
 */
const ILLUSTRATION_PENDING: ReadonlySet<string> = new Set(['tabular-administration']);

describe('blog article illustrations', () => {
  it('names only published slugs in the pending allowlist', () => {
    const slugs = new Set(BLOG_ARTICLES.map(article => article.slug));
    for (const slug of ILLUSTRATION_PENDING) expect(slugs.has(slug), slug).toBe(true);
  });

  it('exist for every article, in every width and as a social image', () => {
    const missing: string[] = [];
    for (const { slug } of BLOG_ARTICLES) {
      if (ILLUSTRATION_PENDING.has(slug)) continue;
      const paths = [
        ...ARTICLE_IMAGE_WIDTHS.map(width => articleImageSrc(slug, width)),
        articleSocialImageSrc(slug),
      ];
      for (const publicPath of paths) {
        if (!existsSync(join(PUBLIC_DIR, publicPath))) missing.push(publicPath);
      }
    }
    expect(missing, 'run: node apps/web/scripts/build-article-images.mjs <masters dir>').toEqual(
      []
    );
  });
});
