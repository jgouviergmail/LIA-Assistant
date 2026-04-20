import pkg from '../../package.json';

/**
 * Application version read directly from package.json.
 * Single source of truth — works in both server and client components
 * without relying on process.env or build-time substitution.
 */
export const APP_VERSION: string = pkg.version;

/**
 * Last update timestamp displayed on the landing page.
 * Updated manually with each release.
 */
export const LAST_UPDATED = '2026-04-20T11:30:00';
