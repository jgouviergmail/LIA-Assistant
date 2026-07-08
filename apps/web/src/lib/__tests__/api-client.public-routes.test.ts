/**
 * Public-route guard — non-regression tests.
 *
 * The api-client 401 handler ejects the visitor to /login on any
 * non-public route. Its public-route list once covered only
 * login/register/root, so every anonymous visitor opening /why, /how,
 * /blog or /faq was silently redirected to the login page in production
 * (the AuthProvider session probe returns 401 for anonymous users).
 *
 * Two layers of protection:
 *  1. explicit behavior pins (public stays, protected redirects),
 *  2. a filesystem completeness scan: every page directory under
 *     `app/[lng]/` that is not in the authenticated set MUST be matched
 *     by `isPublicPath` — adding a new public page without updating the
 *     list fails this test instead of shipping the ejection bug again.
 */

import fs from 'fs';
import path from 'path';
import { describe, it, expect } from 'vitest';
import { isPublicPath } from '../api-client';

/** Route segments that legitimately require an authenticated session. */
const AUTHENTICATED_SEGMENTS = new Set(['dashboard', 'account-inactive']);

/**
 * Collect top-level route segments under `app/[lng]/` that render a page.
 * Route groups like `(auth)` don't appear in URLs — recurse into them.
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

describe('isPublicPath (401 handler public-route guard)', () => {
  it.each([
    '/',
    '/en',
    '/fr/',
    '/why',
    '/en/why',
    '/how',
    '/story',
    '/fr/story',
    '/blog',
    '/blog/mcp-protocol',
    '/en/blog/multi-agent-orchestration',
    '/faq',
    '/privacy',
    '/terms',
    '/login',
    '/es/login',
    '/register',
    '/registration-success',
    '/forgot-password',
    '/reset-password',
    '/verify-email',
    '/oauth-callback',
    '/zh/oauth-callback',
  ])('keeps anonymous visitors on public route %s', pathname => {
    expect(isPublicPath(pathname)).toBe(true);
  });

  it.each([
    '/dashboard',
    '/dashboard/chat',
    '/en/dashboard',
    '/fr/dashboard/settings',
    '/account-inactive',
    '/it/account-inactive',
  ])('redirects to login from protected route %s', pathname => {
    expect(isPublicPath(pathname)).toBe(false);
  });

  it('does not treat lookalike prefixes as public (no substring matching)', () => {
    expect(isPublicPath('/blogus')).toBe(false);
    expect(isPublicPath('/storytelling')).toBe(false);
    expect(isPublicPath('/howto')).toBe(false);
  });

  it('covers every public page directory under app/[lng] (completeness scan)', () => {
    const appDir = path.join(process.cwd(), 'src', 'app', '[lng]');
    const segments = collectRouteSegments(appDir);

    // Sanity: the scan actually found the app tree.
    expect(segments.length).toBeGreaterThan(5);

    const uncovered = segments
      .filter(segment => !AUTHENTICATED_SEGMENTS.has(segment))
      .filter(segment => !isPublicPath(`/${segment}`) || !isPublicPath(`/en/${segment}`));

    // A non-empty list means a new public page would eject anonymous
    // visitors to /login — add its segment to PUBLIC_ROUTE_SEGMENTS
    // in api-client.ts.
    expect(uncovered).toEqual([]);
  });
});
