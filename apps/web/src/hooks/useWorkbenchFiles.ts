'use client';

/**
 * The files screen's reads and acts (ADR-369, Task 8.2).
 *
 * The listing is a cursor page (`useWorkbenchPage`) keyed by what it names — a
 * folder (My Drive when none is), or a Drive-wide search — so a new search
 * never answers with the previous one; a search pages by Drive's cursor too
 * (Drive may answer a partial page before the end). The open folder's own
 * detail gives the breadcrumb. The trash goes through `useApiMutation`, its
 * error rethrown for the screen to say, and re-reads the listing.
 */
import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type {
  WorkbenchActOutcome,
  WorkbenchDriveItem,
  WorkbenchFileDetail,
} from '@/lib/workbench/types';

const FILES_PATH = '/workbench/files';
const FILE_PATH = '/workbench/files/file';

/** What the list shows. */
export type FilesListing =
  | { kind: 'folder'; folderId: string | null }
  | { kind: 'search'; q: string; fullText: boolean };

export interface WorkbenchFilesState {
  list: WorkbenchPageState<WorkbenchDriveItem>;
  /** The open folder, for its breadcrumb; nothing asked at My Drive or during a search. */
  folder: WorkbenchItemState<WorkbenchFileDetail>;
  trash: (ids: string[]) => Promise<WorkbenchActOutcome | undefined>;
}

function paramsOf(listing: FilesListing): Record<string, string> {
  if (listing.kind === 'search') {
    return listing.fullText ? { q: listing.q, full_text: 'true' } : { q: listing.q };
  }
  return listing.folderId ? { folder_id: listing.folderId } : {};
}

export function useWorkbenchFiles(listing: FilesListing): WorkbenchFilesState {
  const params = useMemo(() => paramsOf(listing), [listing]);
  const list = useWorkbenchPage<WorkbenchDriveItem>(FILES_PATH, params);
  const folderId = listing.kind === 'folder' ? listing.folderId : null;
  const folderParams = useMemo(() => ({ id: folderId ?? undefined }), [folderId]);
  const folder = useWorkbenchItem<WorkbenchFileDetail>(folderId ? FILE_PATH : null, folderParams);
  const { refresh } = list;
  const { mutate: post } = useApiMutation<{ file_ids: string[] }, WorkbenchActOutcome>({
    method: 'POST',
    componentName: 'WorkbenchFiles',
  });

  const trash = useCallback(
    async (ids: string[]) => {
      const outcome = await post(`${FILES_PATH}/trash`, { file_ids: ids });
      await refresh();
      return outcome;
    },
    [post, refresh]
  );

  return { list, folder, trash };
}
