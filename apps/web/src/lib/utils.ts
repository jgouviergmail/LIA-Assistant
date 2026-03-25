import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Google image domains that need proxying for COEP: require-corp compatibility.
 */
export const GOOGLE_IMAGE_DOMAINS = [
  'lh3.googleusercontent.com',
  'lh4.googleusercontent.com',
  'lh5.googleusercontent.com',
  'lh6.googleusercontent.com',
];

/**
 * Convert a Google image URL to use our proxy endpoint.
 * This is needed for COEP: require-corp compatibility on Safari iOS.
 *
 * Google's lh3.googleusercontent.com doesn't send CORS headers,
 * so we proxy the image through our backend.
 *
 * @param url - Original image URL
 * @returns Proxied URL if it's a Google image, original URL otherwise
 */
export function proxyGoogleImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;

  try {
    const parsed = new URL(url);
    if (GOOGLE_IMAGE_DOMAINS.includes(parsed.hostname)) {
      // Use the auth proxy endpoint
      return `/api/v1/auth/profile-image-proxy?url=${encodeURIComponent(url)}`;
    }
  } catch {
    // Invalid URL, return as-is
  }

  return url;
}

/**
 * Generate a UUID that works in both secure (HTTPS) and insecure (HTTP) contexts.
 * crypto.randomUUID() only works in secure contexts (HTTPS or localhost).
 * This fallback uses crypto.getRandomValues() which works everywhere.
 */
export function generateUUID(): string {
  // Use native crypto.randomUUID if available (secure context)
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Fallback for insecure contexts (HTTP on non-localhost)
  // Uses crypto.getRandomValues() which is available in all modern browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (crypto.getRandomValues(new Uint8Array(1))[0] & 15) >> (c === 'x' ? 0 : 3);
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/**
 * Normalize text for search: lowercase and remove accents.
 * Useful for case-insensitive, accent-insensitive search.
 *
 * @param text - Text to normalize
 * @returns Normalized text (lowercase, no accents)
 *
 * @example
 * normalizeSearchText('Café') // 'cafe'
 * normalizeSearchText('Gérard') // 'gerard'
 * normalizeSearchText('Ñoño') // 'nono'
 */
export function normalizeSearchText(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, ''); // Remove diacritical marks
}
