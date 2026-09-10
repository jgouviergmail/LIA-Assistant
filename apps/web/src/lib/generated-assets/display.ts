/**
 * How one generated file presents itself (ADR-279).
 *
 * Pure functions, so the naming, the destination and the urgency of an expiry
 * are testable without a grid — and so the gallery and the chat card cannot
 * disagree about where a document opens.
 */

import { apiResourceUrl } from '@/lib/utils/api-resource-url';
import type { GeneratedAsset } from '@/types/generated-assets';

/** Under this many hours left, the deadline is drawn as a warning. */
export const EXPIRY_WARNING_HOURS = 6;

/**
 * What to call a file.
 *
 * @param asset - The file.
 * @returns Its title when its producer knew one, else the download filename —
 *   which is all an upload ever has, and never an empty string.
 */
export function assetLabel(asset: GeneratedAsset): string {
  const title = asset.title?.trim();
  return title || asset.original_filename;
}

/**
 * Where opening a file leads.
 *
 * The SAME rule the chat card follows (ADR-226, amended 2026-08-18): a PDF and
 * an image open their inline attachment URL directly, in the browser's own
 * viewer; every other type opens the document viewer page, which renders csv as
 * a table, markdown through the sanitized pipeline, text as text, and offers an
 * honest download panel for office formats. Two rules would eventually send the
 * same file to two places.
 *
 * @param asset - The file.
 * @param lng - The reader's language, for the viewer route.
 * @returns The href.
 */
export function assetOpenHref(asset: GeneratedAsset, lng: string): string {
  const inline = asset.mime_type.startsWith('image/') || asset.mime_type === 'application/pdf';
  if (inline) return apiResourceUrl(`/api/v1/attachments/${asset.id}`);
  const params = new URLSearchParams({
    name: asset.original_filename,
    type: asset.original_filename.split('.').pop() ?? '',
  });
  return `/${lng}/dashboard/documents/${asset.id}?${params.toString()}`;
}

/**
 * How urgently a deadline reads.
 *
 * @param expiresAt - ISO-8601 instant.
 * @param now - Injected so the threshold is testable in any timezone.
 * @returns The theme-token class the line wears: destructive once it is past,
 *   a warning while it is close, muted otherwise.
 */
export function expiryTone(expiresAt: string, now: number = Date.now()): string {
  const left = new Date(expiresAt).getTime() - now;
  if (!Number.isFinite(left) || left <= 0) return 'text-destructive';
  if (left <= EXPIRY_WARNING_HOURS * 3600 * 1000) return 'text-amber-600 dark:text-amber-500';
  return 'text-muted-foreground';
}
