/**
 * Client-side image compression utility.
 *
 * Uses Canvas API to resize and compress images before upload.
 * Critical for mobile (iPhone photos can be 8MB+, compressed to ~300KB).
 *
 * Phase: evolution F4 — File Attachments & Vision Analysis
 * Created: 2026-03-09
 */

const MAX_DIMENSION = 1600;
const JPEG_QUALITY = 0.82;

/**
 * Compress an image file using Canvas API.
 *
 * - Resizes to max 1600px on longest side
 * - Converts to JPEG at 0.82 quality
 * - iPhone HEIC → JPEG handled automatically by `<input accept="image/*">`
 *
 * @param file - Original image file from input
 * @returns Compressed Blob (JPEG) and dimensions
 */
export async function compressImage(file: File): Promise<{
  blob: Blob;
  width: number;
  height: number;
}> {
  // Skip compression for small files or non-images
  if (!file.type.startsWith('image/') || file.size < 100 * 1024) {
    return { blob: file, width: 0, height: 0 };
  }

  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);

      let { width, height } = img;

      // Scale down if exceeds max dimension
      if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
        const ratio = Math.min(MAX_DIMENSION / width, MAX_DIMENSION / height);
        width = Math.round(width * ratio);
        height = Math.round(height * ratio);
      }

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;

      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('Canvas context unavailable'));
        return;
      }

      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob(
        blob => {
          if (!blob) {
            reject(new Error('Canvas toBlob failed'));
            return;
          }
          resolve({ blob, width, height });
        },
        'image/jpeg',
        JPEG_QUALITY
      );
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Image load failed'));
    };

    img.src = url;
  });
}

/**
 * Check if a file is an image based on MIME type.
 */
export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/');
}

/**
 * Format file size for display (e.g., "2.4 MB", "350 KB").
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
