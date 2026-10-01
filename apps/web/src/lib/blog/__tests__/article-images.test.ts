/**
 * The blog illustrations are pre-generated static variants (ADR-330): the
 * helpers here are the ONE place that spells their names and sizes, so every
 * caller — cards, the article hero, the social metadata — agrees with the
 * files the build script writes.
 */

import { describe, expect, it } from 'vitest';

import {
  ARTICLE_CARD_SIZES,
  ARTICLE_HERO_SIZES,
  ARTICLE_IMAGE_WIDTHS,
  ARTICLE_SOCIAL_IMAGE,
  articleImageSrc,
  articleImageSrcSet,
  articleSocialImageSrc,
  LANDING_CARD_SIZES,
} from '../article-images';

describe('article-images', () => {
  it('names one WebP per declared width, smallest first', () => {
    expect(ARTICLE_IMAGE_WIDTHS).toEqual([480, 768, 1024, 1536]);
    expect(articleImageSrc('sub-agents', 768)).toBe('/articles/sub-agents-768.webp');
    expect(articleImageSrcSet('sub-agents')).toBe(
      '/articles/sub-agents-480.webp 480w, /articles/sub-agents-768.webp 768w, /articles/sub-agents-1024.webp 1024w, /articles/sub-agents-1536.webp 1536w'
    );
  });

  it('names the social image and states its true dimensions', () => {
    expect(articleSocialImageSrc('sub-agents')).toBe('/articles/sub-agents-og.jpg');
    expect(ARTICLE_SOCIAL_IMAGE).toEqual({ width: 1200, height: 675 });
  });

  it('declares sizes that follow the real grids, never a viewport fraction past the cap', () => {
    // The blog grid: 1 / 2 / 3 / 4 columns, capped by max-w-7xl.
    expect(ARTICLE_CARD_SIZES).toBe(
      '(max-width: 640px) 100vw, (max-width: 880px) 50vw, (max-width: 1024px) 33vw, 300px'
    );
    // The landing preview: 1 / 2 / 3 columns, same cap.
    expect(LANDING_CARD_SIZES).toBe('(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 390px');
    // The article hero: the prose column (max-w-3xl).
    expect(ARTICLE_HERO_SIZES).toBe('(max-width: 768px) 100vw, 768px');
  });
});
