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

import type {
  DriveExportFormat,
  WorkbenchDriveItem,
  WorkbenchFileAncestor,
  WorkbenchFileDetail,
} from './types';

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

/** What a drive keeps across its folders. */
export const FILE_VIEWS = ['recent', 'starred', 'shared', 'trash', 'drives'] as const;
export type FileView = (typeof FILE_VIEWS)[number];

/** The view an address names, if it is one. */
export function fileViewOf(raw: string | null): FileView | null {
  return FILE_VIEWS.find(view => view === raw) ?? null;
}

/** One name, never a path: no drive takes a separator in a name. */
export function isOneName(name: string): boolean {
  return !/[/\\]/.test(name);
}

/** The folders down to `folder`, from the top; the top of the drive for none. */
export function trailTo(folder: WorkbenchFileDetail | undefined): WorkbenchFileAncestor[] {
  return folder ? [...folder.ancestors, { id: folder.id, name: folder.name }] : [];
}

/** The folder a file sits in: null at the top of the drive, undefined outside it. */
export function parentOf(file: WorkbenchFileDetail): string | null | undefined {
  const parent = file.ancestors.at(-1);
  if (parent) return parent.id;
  return file.in_my_drive ? null : undefined;
}

/** What a file is to the person who looks at the list. */
export type FileKind =
  | 'folder'
  | 'document'
  | 'spreadsheet'
  | 'presentation'
  | 'pdf'
  | 'image'
  | 'audio'
  | 'video'
  | 'archive'
  | 'file';

/** Words of a type, each naming a kind (Google's and Office's types share them). */
const KIND_WORDS: readonly (readonly [RegExp, FileKind])[] = [
  [/spreadsheet|sheet|excel|csv/, 'spreadsheet'],
  [/presentation|powerpoint/, 'presentation'],
  [/pdf/, 'pdf'],
  [/wordprocessing|msword|google-apps\.document|opendocument\.text|text\//, 'document'],
  [/^image\//, 'image'],
  [/^audio\//, 'audio'],
  [/^video\//, 'video'],
  [/zip|x-tar|x-rar|x-7z|compressed/, 'archive'],
];

/** The folder, or the kind of file, an item shows. */
export function fileKind(
  item: Pick<WorkbenchDriveItem, 'kind' | 'target_kind' | 'mime_type'>
): FileKind {
  if (item.kind === 'folder' || item.target_kind === 'folder') return 'folder';
  return KIND_WORDS.find(([words]) => words.test(item.mime_type))?.[1] ?? 'file';
}

/** How a folder is ordered: by the provider, the listing being paged. */
export type FileOrder = 'name' | 'modified' | 'size';

export const FILE_ORDERS: readonly FileOrder[] = ['name', 'modified', 'size'];

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
