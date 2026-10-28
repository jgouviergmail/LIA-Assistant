/**
 * Hooks for Google Drive folder sync in RAG Spaces.
 *
 * - useDriveSources: mutations for linking, unlinking, and syncing Drive folders.
 * - useDrivePreflight: the exact count a sync would index, asked before it starts.
 * - useDriveFolderBrowser: browsing Drive folders with breadcrumb navigation.
 *
 * Follows the useSpaces / useSpaceDocuments pattern: useApiMutation + apiClient.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useEffectRequest } from '@/hooks/useEffectRequest';

import { useCallback, useState } from 'react';
import { useApiMutation } from './useApiMutation';
import apiClient from '@/lib/api-client';
import type {
  RAGDrivePreflight,
  RAGDriveSource,
  DriveFolder,
  DriveFolderBrowseResponse,
} from '@/types/rag-spaces';

/**
 * Hook for Drive source mutations (link, unlink, sync).
 *
 * Sources data comes from the space detail (loaded by the parent page).
 * This hook only handles mutations.
 */
export function useDriveSources(spaceId: string) {
  const linkMutation = useApiMutation<{ folder_id: string; folder_name: string }, RAGDriveSource>({
    method: 'POST',
    componentName: 'DriveSources',
  });

  const unlinkMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'DriveSources',
  });

  const syncMutation = useApiMutation<void, { sync_status: string }>({
    method: 'POST',
    componentName: 'DriveSources',
  });

  const linkFolder = useCallback(
    async (folderId: string, folderName: string) => {
      return linkMutation.mutate(`/rag-spaces/${spaceId}/drive-sources`, {
        folder_id: folderId,
        folder_name: folderName,
      });
    },
    [spaceId, linkMutation]
  );

  const unlinkFolder = useCallback(
    async (sourceId: string, deleteDocuments = false) => {
      return unlinkMutation.mutate(
        `/rag-spaces/${spaceId}/drive-sources/${sourceId}?delete_documents=${deleteDocuments}`
      );
    },
    [spaceId, unlinkMutation]
  );

  const syncFolder = useCallback(
    async (sourceId: string) => {
      return syncMutation.mutate(`/rag-spaces/${spaceId}/drive-sources/${sourceId}/sync`);
    },
    [spaceId, syncMutation]
  );

  return {
    linkFolder,
    unlinkFolder,
    syncFolder,
    linking: linkMutation.loading,
    unlinking: unlinkMutation.loading,
    syncing: syncMutation.loading,
  };
}

/**
 * What a sync of one folder WOULD index — asked before the sync starts so
 * the person confirms the exact count past the published threshold.
 */
export function useDrivePreflight(spaceId: string) {
  const preflightFolder = useCallback(
    (sourceId: string) =>
      apiClient.get<RAGDrivePreflight>(
        `/rag-spaces/${spaceId}/drive-sources/${sourceId}/preflight`
      ),
    [spaceId]
  );
  return { preflightFolder };
}

/** Breadcrumb entry for Drive folder navigation. */
export interface DriveBreadcrumbEntry {
  id: string;
  /** The folder's Drive name; `null` for the root, whose label the dialog translates. */
  name: string | null;
}

/** Why the current folder could not be listed — a code, worded by whoever draws it. */
export type DriveBrowseError = 'load_failed';

const GOOGLE_FOLDER_MIME = 'application/vnd.google-apps.folder';

const DRIVE_ROOT: DriveBreadcrumbEntry = { id: 'root', name: null };

/** The last answer for one folder: its contents, or why there are none. */
interface DriveListing {
  folderId: string;
  folders: DriveFolder[];
  files: DriveFolder[];
  error: DriveBrowseError | null;
}

/**
 * Hook for browsing Google Drive folders with breadcrumb navigation.
 *
 * Reads only while the picker is open, then the current folder whenever the
 * breadcrumb moves; the picker calls `reset` as it closes, which invalidates
 * what it showed, so the next opening reads again. Every read — the automatic
 * one and `refetch` (the retry) — belongs to one generation
 * (`useEffectRequest`): a later read, a navigation or the closing aborts the
 * one in flight, transport included. An answer is kept per folder, so nothing
 * listed for one folder is ever shown in another, and a retry keeps the
 * failure on screen until its own answer lands.
 *
 * @param spaceId - The space the folder would be linked to.
 * @param open - Whether the picker is open; a closed picker reads nothing.
 */
export function useDriveFolderBrowser(spaceId: string, open: boolean) {
  const [breadcrumb, setBreadcrumb] = useState<DriveBreadcrumbEntry[]>([DRIVE_ROOT]);
  const [listing, setListing] = useState<DriveListing | null>(null);
  const [pending, setPending] = useState(false);

  const currentFolderId = breadcrumb[breadcrumb.length - 1].id;

  const readContents = useCallback(
    async (signal: AbortSignal) => {
      if (!open) return;
      setPending(true);
      try {
        const data = await apiClient.get<DriveFolderBrowseResponse>(
          `/rag-spaces/${spaceId}/drive-browse`,
          { params: { folder_id: currentFolderId }, signal }
        );
        if (signal.aborted) return;
        const all = data?.files ?? [];
        setListing({
          folderId: currentFolderId,
          folders: all.filter(f => f.mimeType === GOOGLE_FOLDER_MIME),
          files: all.filter(f => f.mimeType !== GOOGLE_FOLDER_MIME),
          error: null,
        });
      } catch {
        if (signal.aborted) return;
        setListing({ folderId: currentFolderId, folders: [], files: [], error: 'load_failed' });
      } finally {
        if (!signal.aborted) setPending(false);
      }
    },
    [open, spaceId, currentFolderId]
  );
  const refetch = useEffectRequest(readContents);

  const navigateToFolder = useCallback((folderId: string, folderName: string) => {
    setBreadcrumb(prev => [...prev, { id: folderId, name: folderName }]);
  }, []);

  const navigateBack = useCallback((index: number) => {
    setBreadcrumb(prev => prev.slice(0, index + 1));
  }, []);

  /** Back to the root with nothing shown: called when the picker closes. */
  const reset = useCallback(() => {
    setBreadcrumb([DRIVE_ROOT]);
    setListing(null);
    setPending(false);
  }, []);

  const current = listing?.folderId === currentFolderId ? listing : null;
  return {
    folders: current?.folders ?? [],
    files: current?.files ?? [],
    // A folder nothing has answered for yet is loading from the first frame.
    loading: open && (pending || current === null),
    error: current?.error ?? null,
    breadcrumb,
    currentFolderId,
    navigateToFolder,
    navigateBack,
    reset,
    refetch,
  };
}
