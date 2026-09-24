/**
 * Where the living maps point: their own pages, and the repository.
 *
 * Every brick and every decision has an address the three pages share — a
 * brick is `#<id>` on its map, a decision `#adr-<n>` on the history — so a link
 * works from anywhere: across pages it navigates, on its own page it only moves
 * the hash, which the page listens to.
 */

import type { Language } from '@/i18n/settings';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import type { BrickMapKind, MapPage } from './types';

/** The unlocalized path of the section's home and of each map. */
export const MAPS_HOME_PATH = '/maps';
export const MAP_PAGE_PATHS: Readonly<Record<MapPage, string>> = {
  functional: '/maps/functional',
  technical: '/maps/technical',
  history: '/maps/history',
};

/** The localized path of a page of the section. */
export function mapPageHref(page: MapPage, lng: Language): string {
  return buildLocalizedPath(MAP_PAGE_PATHS[page], lng);
}

/** The hash naming a decision on the history page. */
export const decisionHash = (adr: number): string => `adr-${adr}`;

/** A brick's address: a bare hash on its own map, the map's path elsewhere. */
export function brickHref(id: string, kind: BrickMapKind, from: MapPage, lng: Language): string {
  return kind === from ? `#${id}` : `${mapPageHref(kind, lng)}#${id}`;
}

/** A decision's address in the history. */
export function decisionHref(adr: number, from: MapPage, lng: Language): string {
  const hash = `#${decisionHash(adr)}`;
  return from === 'history' ? hash : `${mapPageHref('history', lng)}${hash}`;
}

/** The decisions that shaped a brick, as a filter of the history. */
export function brickDecisionsHref(id: string, lng: Language): string {
  return `${mapPageHref('history', lng)}#${id}`;
}

/** A decision's file on GitHub — or its row in the ADR index when it has no file. */
export function decisionFileUrl(repo: string, adr: number, file: string | null): string {
  return file
    ? `${repo}docs/architecture/${file}`
    : `${repo}docs/architecture/ADR_INDEX.md#adr-${String(adr).padStart(3, '0')}`;
}

/** A repository path on GitHub. */
export const repoUrl = (repo: string, path: string): string => `${repo}${path}`;

/** A backend domain's directory on GitHub. */
export const domainUrl = (repo: string, domain: string): string =>
  `${repo}apps/api/src/domains/${domain}`;

/** A release's entry in the changelog on GitHub. */
export function releaseUrl(repo: string, version: string, date: string): string {
  return `${repo}CHANGELOG.md#${version.replace(/\./g, '')}---${date}`;
}
