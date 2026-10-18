/**
 * The two questions a bubble asks about bookmarks (ADR-282).
 *
 * The deployment ceiling (`features.bookmarks_enabled`) mounts the routes:
 * under it, what was kept stays readable, deletable and exportable whatever the
 * operator decides — the « Bookmarks » tab of the generated files and the
 * bubble's mark on a kept answer both read it. Only KEEPING a new answer
 * follows the operator's switch, carried by the capability map; an API that
 * omits it falls back to the ceiling alone (the shape of `radioAvailable`).
 * The bubbles used to read the ceiling only, so with the switch off the
 * bookmark stayed offered on every answer and each click was refused.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

export interface BookmarksConfig {
  features?: { bookmarks_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration, or null while it loads.
 * @returns True when the deployment mounts the bookmark routes: kept answers
 *   can be read and let go.
 */
export function bookmarksReadable(config: BookmarksConfig | null | undefined): boolean {
  return Boolean(config?.features?.bookmarks_enabled);
}

/**
 * @param config - The app configuration, or null while it loads.
 * @returns True when keeping a new answer would be accepted (the effective state).
 */
export function bookmarkKeepingAvailable(config: BookmarksConfig | null | undefined): boolean {
  return capabilityEnabled(config?.capabilities, 'bookmarks', bookmarksReadable(config));
}
