/**
 * The files screen's model (ADR-369, Task 8.2).
 *
 * A folder opens in the list and a file in the detail; a shortcut opens what it
 * points at. A download goes through the API's own origin, a Google document in
 * the format asked. A file the provider says is past the ceiling is said so; a
 * Google document, which has no size, never is.
 */

import { describe, expect, it } from 'vitest';

import type { WorkbenchDriveItem } from '@/lib/workbench/types';

import { downloadUrl, fileKind, fileOf, folderOf, instantLabel, isTooLarge } from '../files';

const ITEM: WorkbenchDriveItem = {
  id: 'i1',
  name: 'Budget',
  kind: 'file',
  mime_type: 'application/pdf',
  modified_at: '2026-10-30T09:15:00Z',
  size: 2048,
  web_url: null,
  target_id: null,
  target_kind: null,
  formats: [],
  downloadable: true,
  starred: false,
  previewable: true,
  editable: false,
};

describe('fileKind', () => {
  const kindOf = (mime_type: string) => fileKind({ kind: 'file', target_kind: null, mime_type });

  it('reads what a file is from its type', () => {
    expect(kindOf('application/vnd.google-apps.document')).toBe('document');
    expect(kindOf('application/vnd.google-apps.spreadsheet')).toBe('spreadsheet');
    expect(kindOf('application/vnd.google-apps.presentation')).toBe('presentation');
    expect(kindOf('application/pdf')).toBe('pdf');
    expect(kindOf('image/png')).toBe('image');
    expect(kindOf('audio/mpeg')).toBe('audio');
    expect(kindOf('video/mp4')).toBe('video');
    expect(kindOf('application/zip')).toBe('archive');
    expect(kindOf('application/octet-stream')).toBe('file');
  });

  it('reads an office file by its type as a person calls it', () => {
    expect(kindOf('application/vnd.openxmlformats-officedocument.wordprocessingml.document')).toBe(
      'document'
    );
    expect(kindOf('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')).toBe(
      'spreadsheet'
    );
    expect(
      kindOf('application/vnd.openxmlformats-officedocument.presentationml.presentation')
    ).toBe('presentation');
  });

  it('reads a folder and what a shortcut points at', () => {
    expect(fileKind({ kind: 'folder', target_kind: null, mime_type: 'x' })).toBe('folder');
    expect(fileKind({ kind: 'shortcut', target_kind: 'folder', mime_type: 'x' })).toBe('folder');
  });
});

describe('where an item opens', () => {
  it('opens a folder in the list and a file in the detail', () => {
    const folder = { ...ITEM, kind: 'folder' as const };

    expect([folderOf(folder), fileOf(folder)]).toEqual(['i1', null]);
    expect([folderOf(ITEM), fileOf(ITEM)]).toEqual([null, 'i1']);
  });

  it('opens what a shortcut points at, never the shortcut itself', () => {
    const toFolder = {
      ...ITEM,
      kind: 'shortcut' as const,
      target_id: 'd9',
      target_kind: 'folder' as const,
    };
    const toFile = { ...toFolder, target_id: 'f9', target_kind: 'file' as const };
    const dangling = { ...toFolder, target_id: null, target_kind: null };

    expect([folderOf(toFolder), fileOf(toFolder)]).toEqual(['d9', null]);
    expect([folderOf(toFile), fileOf(toFile)]).toEqual([null, 'f9']);
    expect([folderOf(dangling), fileOf(dangling)]).toEqual([null, null]);
  });
});

describe('downloadUrl', () => {
  it('names the file, and the format of a Google document', () => {
    expect(downloadUrl('a/b?c', null)).toMatch(/\/workbench\/files\/download\?id=a%2Fb%3Fc$/);
    expect(downloadUrl('g1', 'docx')).toMatch(/\/workbench\/files\/download\?id=g1&format=docx$/);
  });
});

describe('isTooLarge', () => {
  it('says so of a file past the ceiling, never of one without a size', () => {
    expect(isTooLarge(ITEM, 2048)).toBe(false);
    expect(isTooLarge(ITEM, 2047)).toBe(true);
    expect(isTooLarge({ ...ITEM, size: null }, 1)).toBe(false);
  });
});

describe('instantLabel', () => {
  it('tells the instant in the account’s zone, and nothing when unreadable', () => {
    expect(instantLabel('2026-10-30T23:30:00Z', 'Asia/Tokyo', 'en')).toContain('Oct 31, 2026');
    expect(instantLabel('2026-10-30T23:30:00Z', 'America/New_York', 'en')).toContain(
      'Oct 30, 2026'
    );
    expect(instantLabel('not a date', 'UTC', 'en')).toBeNull();
    expect(instantLabel(null, 'UTC', 'en')).toBeNull();
  });
});
