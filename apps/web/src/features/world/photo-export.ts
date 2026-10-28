import type { PhotoScene } from './photo-projection';
import { drawPhotoScene } from './photo-renderer';
import { shareNativePhoto } from '@/lib/native/photo';

export const MAX_PHOTO_BYTES = 2 * 1024 * 1024;
export const MAX_PHOTO_EDGE = 1600;
export const PHOTO_ENCODE_TIMEOUT_MS = 5000;
export type PhotoFormat = 'landscape' | 'portrait';
export interface PhotoImage {
  blob: Blob;
  width: number;
  height: number;
}
let busy = false;
interface EncodingLease {
  ended: boolean;
  encoders: number;
}
function release(lease: EncodingLease) {
  if (lease.ended && lease.encoders === 0) busy = false;
}
export function photoSize(format: PhotoFormat, edge: number) {
  if (!Number.isInteger(edge) || edge < 1 || edge > MAX_PHOTO_EDGE)
    throw new Error('world_photo_size');
  return format === 'landscape'
    ? { width: edge, height: Math.round((edge * 9) / 16) }
    : { width: Math.round((edge * 4) / 5), height: edge };
}
function encode(
  canvas: HTMLCanvasElement,
  signal: AbortSignal,
  lease: EncodingLease
): Promise<Blob> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (blob: Blob | null, reason?: string) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      if (reason || !blob || blob.type !== 'image/jpeg' || blob.size === 0)
        reject(new Error('world_photo_' + (reason ?? 'encode')));
      else resolve(blob);
    };
    const abort = () => finish(null, 'aborted');
    const timer = setTimeout(() => finish(null, 'timeout'), PHOTO_ENCODE_TIMEOUT_MS);
    signal.addEventListener('abort', abort, { once: true });
    lease.encoders++;
    const completed = () => {
      lease.encoders--;
      release(lease);
    };
    try {
      canvas.toBlob(
        blob => {
          completed();
          finish(blob);
        },
        'image/jpeg',
        0.9
      );
    } catch {
      completed();
      finish(null, 'encode');
    }
  });
}
function downscale(source: HTMLCanvasElement, size: { width: number; height: number }) {
  const canvas = document.createElement('canvas');
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext('2d', { alpha: false });
  if (!context) throw new Error('world_photo_unavailable');
  context.drawImage(source, 0, 0, size.width, size.height);
  return canvas;
}
export async function renderPhoto(
  scene: PhotoScene,
  format: PhotoFormat,
  signal: AbortSignal
): Promise<PhotoImage> {
  signal.throwIfAborted();
  if (busy) throw new Error('world_photo_busy');
  busy = true;
  const lease: EncodingLease = { ended: false, encoders: 0 };
  let surface: Awaited<ReturnType<typeof drawPhotoScene>> | null = null;
  let scaled: HTMLCanvasElement | null = null;
  try {
    let size = photoSize(format, MAX_PHOTO_EDGE);
    surface = await drawPhotoScene(scene, size, signal);
    signal.throwIfAborted();
    let blob = await encode(surface.canvas, signal, lease);
    if (blob.size > MAX_PHOTO_BYTES) {
      signal.throwIfAborted();
      size = photoSize(format, 960);
      scaled = downscale(surface.canvas, size);
      blob = await encode(scaled, signal, lease);
    }
    signal.throwIfAborted();
    if (blob.size > MAX_PHOTO_BYTES) throw new Error('world_photo_size');
    return { blob, ...size };
  } finally {
    try {
      surface?.dispose();
    } finally {
      try {
        if (scaled) {
          scaled.width = scaled.height = 1;
        }
      } finally {
        // A timed-out native encoder is not cancellable. Retain its lease
        // until its callback settles; repeated opens cannot amplify it.
        lease.ended = true;
        release(lease);
      }
    }
  }
}
export function photoFile(photo: PhotoImage): File {
  return new File([photo.blob], 'lia-world-photo.jpg', { type: 'image/jpeg', lastModified: 0 });
}
export function canShareWorldPhoto(file: File): boolean {
  if (file.type !== 'image/jpeg' || file.size === 0 || file.size > MAX_PHOTO_BYTES) return false;
  try {
    return (
      typeof navigator !== 'undefined' &&
      typeof navigator.share === 'function' &&
      typeof navigator.canShare === 'function' &&
      navigator.canShare({ files: [file] })
    );
  } catch {
    return false;
  }
}
export async function shareWorldPhoto(
  file: File,
  isCurrent: () => boolean = () => true,
  native = false
): Promise<'offered' | 'cancelled' | 'unsupported'> {
  if (!isCurrent()) throw new Error('world_photo_owner');
  if (native) return shareNativePhoto(file, isCurrent);
  if (!canShareWorldPhoto(file)) return 'unsupported';
  if (!isCurrent()) throw new Error('world_photo_owner');
  try {
    await navigator.share({ files: [file], title: 'LIA World' });
    return 'offered';
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled';
    throw error;
  }
}
