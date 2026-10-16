/**
 * A public page settles: every link it shows is prefetched a bounded number of
 * times, never in a loop.
 *
 * The i18n middleware rewrites every default-language path (`/more` →
 * `/fr/more`), so the URL a link carries does not reveal the route it reaches.
 * With Next's optimistic routing on, a link prefetched after the client had
 * learned `/` as `/[lng]` was read as `lng = more`: the predicted page segment
 * answered 404 and the `[lng]` layout segment (1.8 MB) was fetched again about
 * six times per second, for as long as the page stayed open — measured on Next
 * 16.4.1 for /login, /register and /more (`next.config.ts`, `optimisticRouting`).
 *
 * A timeout on `networkidle` only said that something never stopped; this
 * names it: per link and per requested segment, a handful of prefetches at
 * most, and no prefetch that misses its segment.
 */
import type { Page, Request } from '@playwright/test';
import { test, expect } from '../fixtures';

/** What one prefetch asked for: the link's path and the segment it named. */
function prefetchKey(request: Request): string | null {
  const url = new URL(request.url());
  if (!url.searchParams.has('_rsc')) return null;
  const headers = request.headers();
  if (headers['next-router-prefetch'] !== '1') return null;
  return `${url.pathname} ${headers['next-router-segment-prefetch'] ?? '(full)'}`;
}

/** Counts every prefetch the page issues, and every one that missed. */
function watchPrefetches(page: Page) {
  const counts = new Map<string, number>();
  const missed: string[] = [];
  page.on('request', request => {
    const key = prefetchKey(request);
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  page.on('response', response => {
    const key = prefetchKey(response.request());
    if (key && response.status() === 404) missed.push(key);
  });
  return { counts, missed };
}

/** Long enough for a loop to show (it ran at ~6/s), short for a settled page. */
const OBSERVATION_MS = 4_000;
/** A tree, a layout and a page segment, plus one retry: never more. */
const MAX_PER_SEGMENT = 3;

test.describe('public pages settle their prefetches', () => {
  test.use({ viewport: { width: 1280, height: 900 }, locale: 'fr-FR' });

  for (const path of ['/', '/maps/functional']) {
    test(`${path} prefetches each link a bounded number of times`, async ({ page }) => {
      const { counts, missed } = watchPrefetches(page);
      await page.goto(path);
      // Not `awaitStyledPage`: it waits for `networkidle`, which is exactly
      // what a loop prevents — the failure would read as a bare timeout.
      await expect(page.locator('header nav').first()).toBeVisible();
      await page.waitForTimeout(OBSERVATION_MS);

      expect(missed, 'no prefetch asks for a segment the route does not have').toEqual([]);
      const looping = [...counts].filter(([, n]) => n > MAX_PER_SEGMENT);
      expect(looping, 'no link is prefetched in a loop').toEqual([]);
      expect(counts.size, 'the header links were prefetched at all').toBeGreaterThan(0);
    });
  }
});
