/**
 * The public pages of the site are declared ONCE, and every SEO surface reads
 * that declaration.
 *
 * They used to be typed out twice — `sitemap.ts` listed twelve, `robots.ts`
 * listed eleven — and the two lists had already drifted: `/more` and `/demo`
 * were sitemapped but missing from every robots `allow`, and a thirteenth page
 * (`/changelog`) had to be added to both by hand. A second hand-maintained
 * list is how a page ships and is never declared.
 *
 * Three things are pinned here:
 *  1. what the sitemap offers, robots allows — no page announced to crawlers
 *     and then left out of the allow-list;
 *  2. the declaration is complete against the filesystem: every route under
 *     `app/[lng]` is either a declared public page or an explicitly and
 *     justifiably non-indexed one. A new page cannot be silently invisible;
 *  3. the declaration itself is well-formed (absolute paths, no duplicate).
 */

import fs from 'fs';
import path from 'path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { languages } from '@/i18n/settings';

import { NON_INDEXED_SEGMENTS, PUBLIC_PAGES, indexablePathsWithoutHome } from '../public-pages';
import robots from '../../app/robots';
import sitemap from '../../app/sitemap';

/**
 * Top-level route segments under `app/[lng]/` that render a page. Route groups
 * like `(auth)` don't appear in URLs — recurse into them. Same traversal as
 * `api-client.public-routes.test.ts`, which guards the 401 handler against the
 * same class of omission.
 */
function collectRouteSegments(dir: string): string[] {
  const segments: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const full = path.join(dir, entry.name);
    if (entry.name.startsWith('(')) {
      segments.push(...collectRouteSegments(full));
    } else if (fs.existsSync(path.join(full, 'page.tsx'))) {
      segments.push(entry.name);
    }
  }
  return segments;
}

describe('public pages declaration', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('is well-formed: absolute paths, no duplicate, home included', () => {
    const paths = PUBLIC_PAGES.map(page => page.path);

    expect(paths).toContain('/');
    paths.forEach(p => expect(p.startsWith('/')).toBe(true));
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('covers every route under app/[lng] — declared public or deliberately not indexed', () => {
    const segments = collectRouteSegments(path.join(process.cwd(), 'src', 'app', '[lng]'));
    expect(segments.length).toBeGreaterThan(5);

    const declared = new Set(PUBLIC_PAGES.map(page => page.path));
    const undeclared = segments.filter(
      segment => !declared.has(`/${segment}`) && !(segment in NON_INDEXED_SEGMENTS)
    );

    // A non-empty list means a page nobody declared: absent from the sitemap
    // and from robots, so crawlers only ever reach it by luck. Add it to
    // PUBLIC_PAGES, or to NON_INDEXED_SEGMENTS with the reason it stays out.
    expect(undeclared).toEqual([]);
  });

  it('states a reason for every non-indexed route', () => {
    Object.entries(NON_INDEXED_SEGMENTS).forEach(([segment, reason]) => {
      expect(reason.length, `${segment} is excluded without a stated reason`).toBeGreaterThan(10);
    });
  });

  it('allows in robots.txt every page it announces in the sitemap', () => {
    vi.stubEnv('APP_URL_SERVER', 'https://example.test');

    const entries = sitemap();
    const catchAll = robots().rules;
    const rules = Array.isArray(catchAll) ? catchAll : [catchAll];
    const wildcard = rules.find(rule => rule.userAgent === '*');
    const allowed = new Set(
      [wildcard?.allow ?? []].flat().map(rule => rule.replace(/\/\*$/, '') || '/')
    );

    const announced = entries
      .map(entry => new URL(entry.url).pathname)
      .filter(pathname => !pathname.startsWith('/blog/') || pathname === '/blog');
    expect(announced.length).toBeGreaterThan(5);

    const unallowed = announced.filter(pathname => !allowed.has(pathname));
    expect(unallowed).toEqual([]);
  });

  it('allows every declared page in every supported locale', () => {
    // The locale list is `i18n/settings`, not a copy: a seventh language would
    // otherwise ship with none of its pages allowed.
    const rules = [robots().rules].flat();
    const allowed = new Set([rules.find(rule => rule.userAgent === '*')?.allow ?? []].flat());

    languages.forEach(lng =>
      indexablePathsWithoutHome().forEach(p =>
        expect(allowed.has(`/${lng}${p}`), `${lng} misses ${p}`).toBe(true)
      )
    );
  });

  it('serves an honest empty sitemap when no origin is configured', () => {
    vi.stubEnv('APP_URL_SERVER', '');
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '');

    expect(sitemap()).toEqual([]);
  });
});
