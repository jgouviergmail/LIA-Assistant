/**
 * Client-side image download utility.
 *
 * Uses fetch + Blob + programmatic anchor click to trigger a download
 * that works across desktop and mobile browsers, bypassing cross-origin
 * restrictions that prevent the native `<a download>` attribute from working.
 */

/** Map MIME subtypes to file extensions for edge cases. */
const MIME_EXTENSION_MAP: Record<string, string> = {
  jpeg: 'jpg',
  'svg+xml': 'svg',
  'x-icon': 'ico',
};

/**
 * Derive a safe file extension from a MIME type string.
 *
 * Falls back to "png" when the MIME type is missing or unrecognised.
 */
function extensionFromMime(mimeType: string): string {
  const subtype = mimeType.split('/')[1] || 'png';
  return MIME_EXTENSION_MAP[subtype] ?? subtype;
}

/**
 * Sanitise a string for use as a filename.
 *
 * Keeps ASCII alphanumerics, hyphens, underscores, and Unicode letters
 * (accented characters common in French, German, etc.).
 * Collapses consecutive underscores and trims leading/trailing ones.
 */
function sanitiseFilename(raw: string): string {
  return raw
    .replace(/[^\p{L}\p{N}_-]/gu, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

/**
 * Download an image via fetch + blob to bypass cross-origin restrictions
 * that prevent the native `<a download>` attribute from working.
 *
 * Falls back to opening the image in a new tab when the fetch fails
 * (e.g. CORS, network error, non-OK status) so the user can still save manually.
 */
export async function downloadImage(src: string, alt: string): Promise<void> {
  try {
    const response = await fetch(src, { credentials: 'include' });

    if (!response.ok) {
      window.open(src, '_blank');
      return;
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);

    const extension = extensionFromMime(blob.type);
    const baseName = sanitiseFilename(alt) || 'image';

    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = `${baseName}.${extension}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
  } catch {
    // Fallback: open in new tab so the user can save manually
    window.open(src, '_blank');
  }
}
