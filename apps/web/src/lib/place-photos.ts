/** Runtime validation for photo data embedded in sanitized card attributes. */
import { isSafeRedirectUrl } from './safe-navigation';
import { logger } from './logger';

export interface PhotoAuthor {
  name: string;
  url: string;
  avatarUrl?: string;
}

export interface PlacePhoto {
  url: string;
  authors: PhotoAuthor[];
  sourceUrl?: string;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function imageSource(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim() || /[\u0000-\u001f\u007f\\]/.test(value))
    return false;
  try {
    return ['https:', 'http:'].includes(new URL(value, 'https://lia.invalid').protocol);
  } catch {
    return false;
  }
}

function photoAuthors(value: unknown): PhotoAuthor[] {
  if (!Array.isArray(value)) return [];
  const result: PhotoAuthor[] = [];
  for (const author of value) {
    if (!record(author) || typeof author.name !== 'string' || !author.name.trim()) continue;
    result.push({
      name: author.name,
      url: isSafeRedirectUrl(author.url) ? author.url : '',
      avatarUrl: imageSource(author.avatar_url) ? author.avatar_url : undefined,
    });
  }
  return result;
}

export function parsePlacePhotos(value: unknown): PlacePhoto[] {
  if (typeof value !== 'string' || !value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    const photos: PlacePhoto[] = [];
    for (const candidate of parsed) {
      if (imageSource(candidate)) photos.push({ url: candidate, authors: [] });
      else if (record(candidate) && imageSource(candidate.url)) {
        photos.push({
          url: candidate.url,
          authors: photoAuthors(candidate.authors),
          sourceUrl: isSafeRedirectUrl(candidate.source_url) ? candidate.source_url : undefined,
        });
      }
    }
    return photos;
  } catch {
    logger.warn('place_photo_data_invalid', { component: 'PlacePhotoWrapper' });
    return [];
  }
}
