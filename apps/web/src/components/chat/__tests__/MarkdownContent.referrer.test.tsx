/**
 * MarkdownContent — no image leaks the conversation URL (SEC-027).
 *
 * Image sources rendered in chat are frequently third-party and often
 * attacker-influenced: the LLM relays URLs from email bodies, fetched pages and
 * MCP tool output. Loading one sends a `Referer` header carrying the LIA page
 * URL, conversation id included — so a host that never sees the conversation
 * still learns that a given user opened it, and can correlate visits by
 * conversation. `no-referrer` removes the header entirely; nothing about
 * fetching an image needs it.
 *
 * Every rendering branch is covered, because the leak comes from whichever
 * branch actually renders — not from the one that happens to be tested.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

/** Every <img> the given markdown renders. */
function imagesOf(markdown: string): HTMLImageElement[] {
  const { container } = render(<MarkdownContent content={markdown} />);
  return Array.from(container.querySelectorAll('img'));
}

/**
 * Read the policy from the ATTRIBUTE, not the IDL property.
 *
 * jsdom does not reflect `referrerPolicy` onto HTMLImageElement — the property
 * reads back `undefined` even when the attribute is correctly set, so asserting
 * on it would fail against perfectly good markup. The attribute is what a real
 * browser consults anyway, which makes it the more faithful oracle here rather
 * than merely the working one.
 */
function policyOf(img: HTMLImageElement): string | null {
  return img.getAttribute('referrerpolicy');
}

describe('MarkdownContent — Referer is never sent with an image', () => {
  it.each([
    ['a plain markdown image', '![diagram](https://evil.example.com/track.png)'],
    ['a raw HTML image', '<img src="https://evil.example.com/track.png" alt="x">'],
    [
      'a LIA design-system image',
      '<img src="https://evil.example.com/a.png" alt="x" class="lia-avatar--sm">',
    ],
    [
      'a place photo',
      '<img src="https://x.test/api/v1/connectors/google-places/photo?ref=1" alt="place">',
    ],
    [
      'a Google profile photo',
      '<img src="https://lh3.googleusercontent.com/abc" alt="Photo de Jean">',
    ],
  ])('sets referrerPolicy=no-referrer on %s', (_label, markdown) => {
    const images = imagesOf(markdown);

    expect(images.length).toBeGreaterThan(0);
    for (const img of images) {
      expect(policyOf(img)).toBe('no-referrer');
    }
  });

  it('leaves no image in any branch without the policy', () => {
    // A single document exercising several branches at once: the guarantee is
    // "every rendered image", not "the image I remembered to check".
    const markdown = [
      '![one](https://a.test/1.png)',
      '<img src="https://b.test/2.png" alt="two" class="lia-avatar--md">',
      '<img src="https://lh3.googleusercontent.com/three" alt="Photo de X">',
      '<img src="https://c.test/api/v1/connectors/google-places/photo?ref=9" alt="place">',
    ].join('\n\n');

    const images = imagesOf(markdown);

    expect(images.length).toBeGreaterThanOrEqual(4);
    const leaking = images.filter(img => policyOf(img) !== 'no-referrer');
    expect(leaking.map(img => img.getAttribute('src'))).toEqual([]);
  });
});
