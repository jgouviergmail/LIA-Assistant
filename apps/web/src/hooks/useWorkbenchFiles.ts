'use client';

/**
 * The files screen's reads and acts (ADR-369, Task 8.2).
 *
 * The listing is a cursor page (`useWorkbenchPage`) keyed by what it names — a
 * folder (My Drive when none is), or a Drive-wide search — so a new search
 * never answers with the previous one; a search pages by Drive's cursor too
 * (Drive may answer a partial page before the end). The open folder's own
 * detail gives the breadcrumb. The trash and the acts that organise a drive go
 * through `useApiMutation`, their error rethrown for the screen to say, and
 * re-read the listing. What adds an item carries the key the screen holds for
 * its submission.
 */
import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { FileOrder, FileView } from '@/lib/workbench/files';
import type {
  WorkbenchActOutcome,
  WorkbenchDriveItem,
  WorkbenchFileCopied,
  WorkbenchFileDetail,
} from '@/lib/workbench/types';

export const FILES_PATH = '/workbench/files';
const FILE_PATH = '/workbench/files/file';

/** What the list shows. */
export type FilesListing =
  | { kind: 'folder'; folderId: string | null; order: FileOrder }
  | { kind: 'view'; view: FileView }
  | { kind: 'search'; q: string; fullText: boolean };

export interface WorkbenchFilesState {
  list: WorkbenchPageState<WorkbenchDriveItem>;
  /** The open folder, for its breadcrumb; nothing asked at My Drive or during a search. */
  folder: WorkbenchItemState<WorkbenchFileDetail>;
  trash: (ids: string[]) => Promise<WorkbenchActOutcome | undefined>;
  restore: (ids: string[]) => Promise<WorkbenchActOutcome | undefined>;
  deleteForever: (ids: string[]) => Promise<WorkbenchActOutcome | undefined>;
  emptyTrash: () => Promise<void>;
  createFolder: (name: string, folderId: string | null, key: string) => Promise<void>;
  rename: (id: string, name: string) => Promise<void>;
  /** Sets an item's star; the starred view lets go of what loses it. */
  star: (item: WorkbenchDriveItem, starred: boolean) => Promise<void>;
  move: (ids: string[], folderId: string | null) => Promise<WorkbenchActOutcome | undefined>;
  /** Its `item` is null while the provider works on a copy it answered for early. */
  copy: (
    id: string,
    folderId: string | null,
    name: string | undefined,
    key: string
  ) => Promise<WorkbenchFileCopied | undefined>;
}

function paramsOf(listing: FilesListing): Record<string, string> {
  if (listing.kind === 'view') return { view: listing.view };
  if (listing.kind === 'search') {
    return listing.fullText ? { q: listing.q, full_text: 'true' } : { q: listing.q };
  }
  return {
    ...(listing.folderId ? { folder_id: listing.folderId } : {}),
    ...(listing.order === 'name' ? {} : { order: listing.order }),
  };
}

export function useWorkbenchFiles(listing: FilesListing): WorkbenchFilesState {
  const params = useMemo(() => paramsOf(listing), [listing]);
  const list = useWorkbenchPage<WorkbenchDriveItem>(FILES_PATH, params);
  const folderId = listing.kind === 'folder' ? listing.folderId : null;
  const folderParams = useMemo(() => ({ id: folderId ?? undefined }), [folderId]);
  const folder = useWorkbenchItem<WorkbenchFileDetail>(folderId ? FILE_PATH : null, folderParams);
  const { refresh, replaceItem } = list;
  const leavesView = listing.kind === 'view' && listing.view === 'starred';
  const { mutate: post } = useApiMutation<object, WorkbenchActOutcome>({
    method: 'POST',
    componentName: 'WorkbenchFiles',
  });
  const { mutate: postCopy } = useApiMutation<object, WorkbenchFileCopied>({
    method: 'POST',
    componentName: 'WorkbenchFiles',
  });
  const { mutate: patch } = useApiMutation<object, WorkbenchDriveItem>({
    method: 'PATCH',
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

  const restore = useCallback(
    async (ids: string[]) => {
      const outcome = await post(`${FILES_PATH}/restore`, { file_ids: ids });
      await refresh();
      return outcome;
    },
    [post, refresh]
  );

  const deleteForever = useCallback(
    async (ids: string[]) => {
      const outcome = await post(`${FILES_PATH}/delete`, { file_ids: ids });
      await refresh();
      return outcome;
    },
    [post, refresh]
  );

  const emptyTrash = useCallback(async () => {
    await post(`${FILES_PATH}/trash/empty`);
    await refresh();
  }, [post, refresh]);

  const createFolder = useCallback(
    async (name: string, folderId: string | null, key: string) => {
      await post(`${FILES_PATH}/folders`, { name, folder_id: folderId, idempotency_key: key });
      await refresh();
    },
    [post, refresh]
  );

  const rename = useCallback(
    async (id: string, name: string) => {
      await patch(FILE_PATH, { file_id: id, name });
      await refresh();
    },
    [patch, refresh]
  );

  const star = useCallback(
    async (item: WorkbenchDriveItem, starred: boolean) => {
      await patch(`${FILES_PATH}/star`, { file_id: item.id, starred });
      replaceItem(item.id, leavesView && !starred ? null : { ...item, starred });
    },
    [leavesView, patch, replaceItem]
  );

  const move = useCallback(
    async (ids: string[], folderId: string | null) => {
      const outcome = await post(`${FILES_PATH}/move`, { file_ids: ids, folder_id: folderId });
      await refresh();
      return outcome;
    },
    [post, refresh]
  );

  const copy = useCallback(
    async (id: string, folderId: string | null, name: string | undefined, key: string) => {
      const copied = await postCopy(`${FILES_PATH}/copy`, {
        file_id: id,
        folder_id: folderId,
        name,
        idempotency_key: key,
      });
      await refresh();
      return copied;
    },
    [postCopy, refresh]
  );

  return {
    list,
    folder,
    trash,
    restore,
    deleteForever,
    emptyTrash,
    createFolder,
    rename,
    star,
    move,
    copy,
  };
}
