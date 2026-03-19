import pkg from '../../package.json';

/**
 * Application version read directly from package.json.
 * Single source of truth — works in both server and client components
 * without relying on process.env or build-time substitution.
 */
export const APP_VERSION: string = pkg.version;
