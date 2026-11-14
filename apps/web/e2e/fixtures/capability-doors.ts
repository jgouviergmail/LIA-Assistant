/**
 * What the « capability door » journeys share (ADR-280).
 *
 * An operator switch closes a capability's routes while its deployment flag
 * still mounts them. These journeys prove, in a browser, that what the switch
 * closed is offered nowhere and asked by nobody — so they all need the same
 * three things: the labels a reader sees, a `/config` carrying the operator's
 * verdicts, and the list of requests that left for a closed router.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import type { Page } from '@playwright/test';

import type { MockRoute } from './api-mock';
import { appConfig } from './dashboard-shell';

const dictionary: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);

/**
 * A French label, read from the locale file the page renders from.
 *
 * @param key - The dotted i18n key.
 * @returns The text a French reader sees.
 */
export function label(key: string): string {
  let value: unknown = dictionary;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing label ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing label ${key}`);
  return value;
}

/** Every capability these journeys switch, mounted by the deployment. */
const MOUNTED = {
  channels_enabled: true,
  journals_enabled: true,
  skills_enabled: true,
  rag_spaces_enabled: true,
  telephony_enabled: true,
  mcp_user_enabled: true,
} as const;

/** A flag of the deployment a journey leaves off. */
export type Unmounted = Partial<Record<keyof typeof MOUNTED, false>>;

/** The capabilities whose switch the journeys flip, as `/config` keys them. */
export const SWITCHED = [
  'channels',
  'psyche',
  'journals',
  'skills',
  'mcp',
  'rag_spaces',
  'image_generation',
  'telephony',
] as const;
export type Switched = (typeof SWITCHED)[number];

/**
 * A `/config` of a deployment that mounts everything, with the operator's verdicts.
 *
 * @param switchedOff - The capabilities the operator switched off.
 * @param unmounted - The flags this deployment leaves off (default: none).
 * @returns The mock route to register after `authenticate`.
 */
export function configRoute(
  switchedOff: readonly Switched[],
  unmounted: Unmounted = {}
): MockRoute {
  return {
    url: '**/api/v1/config',
    json: {
      ...appConfig,
      features: { ...appConfig.features, ...MOUNTED, ...unmounted },
      capabilities: Object.fromEntries(
        SWITCHED.map(key => [key, { enabled: !switchedOff.includes(key), family: 'x' }])
      ),
    },
  };
}

/** The routers those switches close, reads included. */
const CLOSED_ROUTER =
  /\/api\/v1\/(channels|psyche|journals|skills|mcp\/servers|rag-spaces|image-generation|telephony)(?=[/?]|$)/;

/**
 * Record every request the page sends to a router a switch can close.
 *
 * @param page - The page under test; call before the first navigation.
 * @returns The live list of request paths, in the order they left.
 */
export function watchClosedRouters(page: Page): string[] {
  const asked: string[] = [];
  page.on('request', request => {
    if (CLOSED_ROUTER.test(request.url())) asked.push(new URL(request.url()).pathname);
  });
  return asked;
}
