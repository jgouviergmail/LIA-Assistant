'use client';

import { useCallback, useEffect, useRef, useState, use } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useSpaceDetail } from '@/hooks/useSpaces';
import { useSpaceDocuments } from '@/hooks/useSpaceDocuments';
import { useDriveSources } from '@/hooks/useDriveSources';
import { ArrowLeft, Pencil, Trash2, Library } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Card, CardHeader } from '@/components/ui/card';
import { SpaceActivationToggle } from '@/components/spaces/SpaceActivationToggle';
import { DocumentUploadZone } from '@/components/spaces/DocumentUploadZone';
import { DocumentRow } from '@/components/spaces/DocumentRow';
import { DriveSourcesList } from '@/components/spaces/DriveSourcesList';
import { EditSpaceDialog } from '@/components/spaces/EditSpaceDialog';
import { DeleteSpaceConfirm } from '@/components/spaces/DeleteSpaceConfirm';
import { FeatureErrorBoundary } from '@/components/errors';
import { useApiMutation } from '@/hooks/useApiMutation';
import { formatFileSize } from '@/lib/format';
import { toast } from 'sonner';
import type { RAGSpaceToggleResponse } from '@/types/rag-spaces';

interface SpaceDetailPageProps {
  params: Promise<{ lng: string; id: string }>;
}

export default function SpaceDetailPage({ params }: SpaceDetailPageProps) {
  const resolvedParams = use(params);
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const spaceId = resolvedParams.id;

  const { space, loading, refetch, setData } = useSpaceDetail(spaceId);

  const { uploads, uploadDocument, deleteDocument, dismissUpload, deleting } =
    useSpaceDocuments({
      spaceId,
      documents: space?.documents ?? [],
      onDocumentReady: refetch,
    });

  // Space mutations
  const toggleMutation = useApiMutation<void, RAGSpaceToggleResponse>({
    method: 'PATCH',
    componentName: 'SpaceDetail',
  });

  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'SpaceDetail',
  });

  const updateMutation = useApiMutation<{ name?: string; description?: string }, unknown>({
    method: 'PATCH',
    componentName: 'SpaceDetail',
  });

  // Drive sources mutations
  const { linkFolder, unlinkFolder, syncFolder, linking, syncing } = useDriveSources(spaceId);

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Poll for sync status when any drive source is syncing
  const driveSources = space?.drive_sources ?? [];
  const hasSyncingSource = driveSources.some((s) => s.sync_status === 'syncing');
  const refetchRef = useRef(refetch);
  useEffect(() => {
    refetchRef.current = refetch;
  }, [refetch]);

  useEffect(() => {
    if (!hasSyncingSource) return;
    const interval = setInterval(() => {
      refetchRef.current();
    }, 5_000);
    return () => clearInterval(interval);
  }, [hasSyncingSource]);

  const handleToggle = useCallback(async () => {
    if (!space) return;
    const result = await toggleMutation.mutate(`/rag-spaces/${spaceId}/toggle`);
    if (result) {
      setData((prev) => prev ? { ...prev, is_active: result.is_active } : prev);
      toast.success(
        result.is_active
          ? t('spaces.toggle_activated', { name: space.name })
          : t('spaces.toggle_deactivated', { name: space.name })
      );
    }
  }, [space, spaceId, toggleMutation, setData, t]);

  const handleUpdate = useCallback(
    async (name?: string, description?: string) => {
      try {
        await updateMutation.mutate(`/rag-spaces/${spaceId}`, { name, description });
        toast.success(t('spaces.edit_success'));
        refetch();
      } catch {
        toast.error(t('spaces.edit_error'));
      }
    },
    [spaceId, updateMutation, refetch, t]
  );

  const handleDelete = useCallback(async () => {
    try {
      await deleteMutation.mutate(`/rag-spaces/${spaceId}`);
      toast.success(t('spaces.delete_success', { name: space?.name }));
      router.push('/dashboard/spaces');
    } catch {
      toast.error(t('spaces.delete_error'));
    }
  }, [spaceId, deleteMutation, space, router, t]);

  const handleDeleteDocument = useCallback(
    async (documentId: string) => {
      try {
        await deleteDocument(documentId);
        toast.success(t('spaces.documents.delete_success'));
      } catch {
        toast.error(t('spaces.documents.delete_error'));
      }
    },
    [deleteDocument, t]
  );

  const handleUpload = useCallback(
    async (file: File) => {
      const result = await uploadDocument(file);
      if (result.success) {
        toast.success(t('spaces.documents.upload_success', { name: file.name }));
      } else if (result.error) {
        toast.error(t('spaces.documents.upload_error', { name: file.name }));
      }
      return result;
    },
    [uploadDocument, t]
  );

  const handleLinkFolder = useCallback(
    async (folderId: string, folderName: string) => {
      try {
        await linkFolder(folderId, folderName);
        toast.success(t('spaces.drive.link_success', { name: folderName }));
        refetch();
      } catch {
        toast.error(t('spaces.drive.link_error'));
      }
    },
    [linkFolder, refetch, t]
  );

  const handleUnlinkFolder = useCallback(
    async (sourceId: string, deleteDocuments: boolean) => {
      const source = driveSources.find((s) => s.id === sourceId);
      try {
        await unlinkFolder(sourceId, deleteDocuments);
        toast.success(t('spaces.drive.unlink_success', { name: source?.folder_name ?? '' }));
        refetch();
      } catch {
        toast.error(t('spaces.drive.link_error'));
      }
    },
    [unlinkFolder, driveSources, refetch, t]
  );

  const handleSyncFolder = useCallback(
    async (sourceId: string) => {
      const source = driveSources.find((s) => s.id === sourceId);
      try {
        await syncFolder(sourceId);
        toast.success(t('spaces.drive.syncing'));
        refetch();
      } catch {
        toast.error(t('spaces.drive.sync_error', { name: source?.folder_name ?? '' }));
      }
    },
    [syncFolder, driveSources, refetch, t]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner size="xl" />
      </div>
    );
  }

  if (!space) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">{t('spaces.not_found')}</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push('/dashboard/spaces')}>
          {t('common.back')}
        </Button>
      </div>
    );
  }

  return (
    <FeatureErrorBoundary feature="rag-spaces-detail">
      <div className="space-y-6">
        {/* Breadcrumb */}
        <Button
          variant="ghost"
          className="gap-2 -ml-3"
          onClick={() => router.push('/dashboard/spaces')}
        >
          <ArrowLeft className="h-4 w-4" />
          {t('spaces.back_to_spaces')}
        </Button>

        {/* Header */}
        <Card>
          <CardHeader className="p-4 sm:p-6 flex-row items-start gap-4 space-y-0">
            <div className="rounded-lg bg-primary/10 p-3 shrink-0">
              <Library className="h-6 w-6 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold truncate">{space.name}</h1>
              {space.description && (
                <p className="mt-1 text-muted-foreground">{space.description}</p>
              )}
              <div className="flex items-center gap-3 mt-3 text-sm text-muted-foreground">
                <Badge variant={space.is_active ? 'success' : 'outline'}>
                  {space.is_active ? t('common.active') : t('common.inactive')}
                </Badge>
                <span>
                  {space.document_count}{' '}
                  {space.document_count === 1 ? t('spaces.doc_singular') : t('spaces.docs_plural')}
                </span>
                {space.total_size > 0 && <span>{formatFileSize(space.total_size)}</span>}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <SpaceActivationToggle
                isActive={space.is_active}
                onToggle={handleToggle}
                disabled={toggleMutation.loading}
              />
              <Button variant="ghost" size="icon" onClick={() => setEditOpen(true)} aria-label={t('common.edit')}>
                <Pencil className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setDeleteOpen(true)} aria-label={t('common.delete')}>
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          </CardHeader>
        </Card>

        {/* Upload Zone */}
        <DocumentUploadZone
          onUpload={handleUpload}
          uploads={uploads}
          onDismissUpload={dismissUpload}
        />

        {/* Google Drive Sources */}
        <DriveSourcesList
          spaceId={spaceId}
          sources={driveSources}
          onLink={handleLinkFolder}
          onUnlink={handleUnlinkFolder}
          onSync={handleSyncFolder}
          linking={linking}
          syncing={syncing}
        />

        {/* Documents list */}
        {space.documents.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm text-muted-foreground">{t('spaces.documents.empty')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {space.documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                document={doc}
                onDelete={handleDeleteDocument}
                deleting={deleting}
              />
            ))}
          </div>
        )}

        {/* Dialogs */}
        <EditSpaceDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          space={space}
          onSubmit={handleUpdate}
          isLoading={updateMutation.loading}
        />

        <DeleteSpaceConfirm
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          spaceName={space.name}
          onConfirm={handleDelete}
        />
      </div>
    </FeatureErrorBoundary>
  );
}
