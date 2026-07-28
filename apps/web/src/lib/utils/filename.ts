/**
 * Filename sanitisation shared by the client-side download helpers
 * (image download, markdown export).
 */

/**
 * Sanitise a string for use as a filename.
 *
 * Keeps ASCII alphanumerics, hyphens, underscores, and Unicode letters
 * (accented characters common in French, German, etc.).
 * Collapses consecutive underscores and trims leading/trailing ones.
 */
export function sanitiseFilename(raw: string): string {
  return raw
    .replace(/[^\p{L}\p{N}_-]/gu, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}
