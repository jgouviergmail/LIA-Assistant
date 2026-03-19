/**
 * Hooks for Google Drive folder sync in RAG Spaces.
 *
 * - useDriveSources: mutations for linking, unlinking, and syncing Drive folders.
 * - useDriveFolderBrowser: browsing Drive folders with breadcrumb navigation.
 *
 * Follows the useSpaces / useSpaceDocuments pattern: useApiMutation + apiClient.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import { useApiMutation } from './useApiMutation';
import apiClient from '@/lib/api-client';
import type { RAGDriveSource, DriveFolder, DriveFolderBrowseResponse } from '@/types/rag-spaces';

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

/** Breadcrumb entry for Drive folder navigation. */
export interface DriveBreadcrumbEntry {
  id: string;
  name: string;
}

/**
 * Hook for browsing Google Drive folders with breadcrumb navigation.
 *
 * Auto-fetches folders whenever the current breadcrumb position changes.
 */
const GOOGLE_FOLDER_MIME = 'application/vnd.google-apps.folder';

export function useDriveFolderBrowser(spaceId: string) {
  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [files, setFiles] = useState<DriveFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [breadcrumb, setBreadcrumb] = useState<DriveBreadcrumbEntry[]>([
    { id: 'root', name: 'My Drive' },
  ]);

  const currentFolderId = breadcrumb[breadcrumb.length - 1].id;

  const fetchContents = useCallback(
    async (folderId: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient.get<DriveFolderBrowseResponse>(
          `/rag-spaces/${spaceId}/drive-browse`,
          { params: { folder_id: folderId } }
        );
        const all = data?.files ?? [];
        setFolders(all.filter(f => f.mimeType === GOOGLE_FOLDER_MIME));
        setFiles(all.filter(f => f.mimeType !== GOOGLE_FOLDER_MIME));
      } catch {
        setError('Failed to load folders');
        setFolders([]);
        setFiles([]);
      } finally {
        setLoading(false);
      }
    },
    [spaceId]
  );

  const navigateToFolder = useCallback((folderId: string, folderName: string) => {
    setBreadcrumb(prev => [...prev, { id: folderId, name: folderName }]);
  }, []);

  const navigateBack = useCallback((index: number) => {
    setBreadcrumb(prev => prev.slice(0, index + 1));
  }, []);

  const reset = useCallback(() => {
    setBreadcrumb([{ id: 'root', name: 'My Drive' }]);
    setFolders([]);
    setFiles([]);
    setError(null);
  }, []);

  // Auto-fetch when breadcrumb changes
  useEffect(() => {
    fetchContents(currentFolderId);
  }, [currentFolderId, fetchContents]);

  return {
    folders,
    files,
    loading,
    error,
    breadcrumb,
    currentFolderId,
    navigateToFolder,
    navigateBack,
    reset,
    refetch: () => fetchContents(currentFolderId),
  };
}
