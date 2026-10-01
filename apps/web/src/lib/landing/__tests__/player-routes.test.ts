/**
 * Where the persistent landing player may live (ADR-330 amendment): the
 * public pages, by a declared list — and every route under `app/[lng]` chose
 * a side, so a page added later cannot keep the music by accident, nor lose
 * the player in silence.
 */

import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { PLAYER_STOP_ROUTES, PUBLIC_PLAYER_ROUTES, playerRouteKind } from '../player-routes';

describe('playerRouteKind', () => {
  it.each([
    ['/fr', 'public'],
    ['/fr/', 'public'],
    ['/en/blog/some-slug', 'public'],
    ['/de/maps/history', 'public'],
    ['/zh/faq?open=1', 'public'],
    ['/it/story#part-2', 'public'],
    ['/fr/login', 'stop'],
    ['/fr/register', 'stop'],
    ['/fr/dashboard/chat', 'stop'],
    ['/fr/share?x=1', 'stop'],
    ['/fr/account-inactive', 'stop'],
    ['/fr/some-page-nobody-declared', 'stop'],
    // The default language is served without its prefix (measured on dev).
    ['/', 'public'],
    ['', 'public'],
    ['/blog/some-slug', 'public'],
    ['/maps', 'public'],
    ['/login', 'stop'],
    ['/dashboard/chat', 'stop'],
    ['/some-page-nobody-declared', 'stop'],
  ] as const)('%s → %s', (path, kind) => {
    expect(playerRouteKind(path)).toBe(kind);
  });
});

describe('every route under app/[lng] chose a side', () => {
  // vitest runs from apps/web; `import.meta.url` is not a file URL under its transform.
  const appDir = join(process.cwd(), 'src', 'app', '[lng]');
  const directoriesOf = (dir: string) =>
    readdirSync(dir).filter(
      name =>
        !name.startsWith('__') && !name.startsWith('(') && statSync(join(dir, name)).isDirectory()
    );
  const routes = [...directoriesOf(appDir), ...directoriesOf(join(appDir, '(auth)'))];

  it('names each top-level route and each (auth) page in exactly one of the two lists', () => {
    const declared = new Set<string>([...PUBLIC_PLAYER_ROUTES, ...PLAYER_STOP_ROUTES]);
    for (const route of routes) {
      expect(declared.has(route), `route "${route}" is on neither list`).toBe(true);
    }
    for (const route of declared) {
      // '' is the landing itself: a route with no second segment.
      expect(route === '' || routes.includes(route), `"${route}" names no route`).toBe(true);
    }
    expect(PUBLIC_PLAYER_ROUTES.filter(route => PLAYER_STOP_ROUTES.includes(route))).toEqual([]);
  });
});
