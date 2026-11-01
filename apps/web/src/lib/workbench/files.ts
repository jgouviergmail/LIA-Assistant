/**
 * The files screen's model (ADR-369): pure.
 *
 * A folder opens IN the list (`?folder=`), a file in the detail (`?file=`); a
 * shortcut opens what it points at — its target folder in the list, its target
 * file in the detail. A download goes through the API's own origin
 * (`apiEndpointUrl`, never a relative path): a Google document once per format
 * it exports to, any other file as itself, and none the provider says is
 * larger than the published ceiling (ADR-184).
 */
import { getIntlLocale, type Language } from '@/i18n/settings';
import { apiEndpointUrl } from '@/lib/api-client';

import type { DriveExportFormat, WorkbenchDriveItem } from './types';

/** The folder an item opens in the list, if it is one (or a shortcut to one). */
export function folderOf(item: WorkbenchDriveItem): string | null {
  if (item.kind === 'folder') return item.id;
  return item.kind === 'shortcut' && item.target_kind === 'folder' ? item.target_id : null;
}

/** The file an item opens in the detail, if it is one (or a shortcut to one). */
export function fileOf(item: WorkbenchDriveItem): string | null {
  if (item.kind === 'file') return item.id;
  return item.kind === 'shortcut' && item.target_kind === 'file' ? item.target_id : null;
}

/** The download of a file, a Google document in the format asked. */
export function downloadUrl(id: string, format: DriveExportFormat | null): string {
  const query = new URLSearchParams({ id });
  if (format) query.set('format', format);
  return apiEndpointUrl(`/workbench/files/download?${query.toString()}`);
}

/** The provider says the file is larger than the published ceiling. */
export function isTooLarge(item: WorkbenchDriveItem, maxBytes: number): boolean {
  return item.size !== null && item.size > maxBytes;
}

/** An instant as the detail tells it, in the account's zone; null when unreadable. */
export function instantLabel(
  iso: string | null,
  zone: string | undefined,
  lng: Language
): string | null {
  const instant = iso ? new Date(iso) : null;
  if (!instant || Number.isNaN(instant.getTime())) return null;
  return new Intl.DateTimeFormat(getIntlLocale(lng), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: zone,
  }).format(instant);
}
