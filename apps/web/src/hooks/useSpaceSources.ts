/**
 * Everything a space page needs about its synced sources, in one hook.
 *
 * The page was accumulating it inline — two source lists, the instance gate
 * for Gmail labels (ADR-262), the poll that refreshes while a sync runs, and
 * six action handlers — which is what pushed the component past the frontend
 * complexity ratchet. The page now asks one question and renders; the rules
 * live here, testable on their own.
 */

'use client';

import { useEffect, useMemo, useRef } from 'react';

import { useAppConfig } from '@/hooks/useAppConfig';
import { useDriveSources } from '@/hooks/useDriveSources';
import { useMailSources } from '@/hooks/useMailSources';
import { useSourceActions, type SourceActions } from '@/hooks/useSourceActions';
import type { RAGDriveSource, RAGMailSource, RAGSpaceDetail } from '@/types/rag-spaces';

/** How often the detail is refetched while any source reports `syncing`. */
const SYNC_POLL_MS = 5_000;

export interface SpaceSources {
  driveSources: RAGDriveSource[];
  mailSources: RAGMailSource[];
  /** The instance runs the Gmail label source — the section exists only then. */
  mailSyncEnabled: boolean;
  drive: SourceActions & { linking: boolean; syncing: boolean };
  mail: SourceActions & { linking: boolean; syncing: boolean };
}

export function useSpaceSources(
  spaceId: string,
  space: RAGSpaceDetail | null | undefined,
  refetch: () => void
): SpaceSources {
  const {
    linkFolder,
    unlinkFolder,
    syncFolder,
    linking: linkingFolder,
    syncing: syncingFolder,
  } = useDriveSources(spaceId);
  const {
    linkLabel,
    unlinkLabel,
    syncLabel,
    linking: linkingLabel,
    syncing: syncingLabel,
  } = useMailSources(spaceId);

  const { config } = useAppConfig();
  const mailSyncEnabled = config?.features?.rag_spaces_mail_sync_enabled ?? false;

  const driveSources = useMemo(() => space?.drive_sources ?? [], [space?.drive_sources]);
  const mailSources = useMemo(() => space?.mail_sources ?? [], [space?.mail_sources]);

  // Refresh while anything is syncing — the status lives server-side.
  const isSyncing = (source: { sync_status: string }) => source.sync_status === 'syncing';
  const hasSyncingSource = driveSources.some(isSyncing) || mailSources.some(isSyncing);
  const refetchRef = useRef(refetch);
  useEffect(() => {
    refetchRef.current = refetch;
  }, [refetch]);
  useEffect(() => {
    if (!hasSyncingSource) return;
    const interval = setInterval(() => refetchRef.current(), SYNC_POLL_MS);
    return () => clearInterval(interval);
  }, [hasSyncingSource]);

  const driveActions = useSourceActions({
    sources: driveSources,
    namespace: 'spaces.drive',
    nameOf: source => source.folder_name,
    link: linkFolder,
    unlink: unlinkFolder,
    sync: syncFolder,
    refetch,
  });

  const mailActions = useSourceActions({
    sources: mailSources,
    namespace: 'spaces.mail',
    nameOf: source => source.label_name,
    link: linkLabel,
    unlink: unlinkLabel,
    sync: syncLabel,
    refetch,
  });

  return {
    driveSources,
    mailSources,
    mailSyncEnabled,
    drive: { ...driveActions, linking: linkingFolder, syncing: syncingFolder },
    mail: { ...mailActions, linking: linkingLabel, syncing: syncingLabel },
  };
}
