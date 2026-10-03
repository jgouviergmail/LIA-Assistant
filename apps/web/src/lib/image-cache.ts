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
/** Metadata hints only; browser HTTP caching remains responsible for the pixels. */
export const MAX_LOADED_IMAGES = 512;
const loadedImagesCache = new Set<string>();

/**
 * Check if an image has been loaded.
 */
export function isImageLoaded(src: string): boolean {
  if (!loadedImagesCache.has(src)) return false;
  loadedImagesCache.delete(src);
  loadedImagesCache.add(src);
  return true;
}

/**
 * Mark an image as loaded.
 */
export function markImageLoaded(src: string): void {
  if (!src) return;
  loadedImagesCache.delete(src);
  loadedImagesCache.add(src);
  if (loadedImagesCache.size > MAX_LOADED_IMAGES) {
    const oldest = loadedImagesCache.values().next().value;
    if (oldest !== undefined) loadedImagesCache.delete(oldest);
  }
}
