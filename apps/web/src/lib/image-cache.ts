/**
 * Global image loading cache.
 *
 * Tracks which images have been loaded to prevent flash/scintillation
 * during React re-renders (especially during streaming).
 *
 * Used by:
 * - MarkdownContent (contact photos, place photos)
 * - InlinePlaceCarousel (carousel images)
 *
 * @see Issue #64 - Images flashing during streaming
 */
export const loadedImagesCache = new Set<string>();

/**
 * Check if an image has been loaded.
 */
export function isImageLoaded(src: string): boolean {
  return loadedImagesCache.has(src);
}

/**
 * Mark an image as loaded.
 */
export function markImageLoaded(src: string): void {
  loadedImagesCache.add(src);
}
