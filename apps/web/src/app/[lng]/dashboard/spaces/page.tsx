'use client';

import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useSpaces } from '@/hooks/useSpaces';
import { Library, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SpaceCard } from '@/components/spaces/SpaceCard';
import { CreateSpaceDialog } from '@/components/spaces/CreateSpaceDialog';
import { EditSpaceDialog } from '@/components/spaces/EditSpaceDialog';
import { DeleteSpaceConfirm } from '@/components/spaces/DeleteSpaceConfirm';
import { FeatureErrorBoundary } from '@/components/errors';
import { toast } from 'sonner';
import type { RAGSpace } from '@/types/rag-spaces';

export default function SpacesPage() {
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const {
    spaces,
    loading,
    createSpace,
    updateSpace,
    deleteSpace,
    toggleSpace,
    creating,
    updating,
    toggling,
  } = useSpaces();

  // Dialog states
  const [createOpen, setCreateOpen] = useState(false);
  const [editSpace, setEditSpace] = useState<RAGSpace | null>(null);
  const [deleteConfirmSpace, setDeleteConfirmSpace] = useState<RAGSpace | null>(null);

  const handleCreate = useCallback(
    async (name: string, description?: string) => {
      try {
        await createSpace({ name, description });
        toast.success(t('spaces.create_success', { name }));
      } catch {
        toast.error(t('spaces.create_error'));
      }
    },
    [createSpace, t]
  );

  const handleUpdate = useCallback(
    async (name?: string, description?: string) => {
      if (!editSpace) return;
      try {
        await updateSpace(editSpace.id, { name, description });
        toast.success(t('spaces.edit_success'));
        setEditSpace(null);
      } catch {
        toast.error(t('spaces.edit_error'));
      }
    },
    [editSpace, updateSpace, t]
  );

  const handleDelete = useCallback(async () => {
    if (!deleteConfirmSpace) return;
    try {
      await deleteSpace(deleteConfirmSpace.id);
      toast.success(t('spaces.delete_success', { name: deleteConfirmSpace.name }));
    } catch {
      toast.error(t('spaces.delete_error'));
    }
    setDeleteConfirmSpace(null);
  }, [deleteConfirmSpace, deleteSpace, t]);

  const handleToggle = useCallback(
    async (spaceId: string) => {
      try {
        const result = await toggleSpace(spaceId);
        if (result) {
          const space = spaces.find((s) => s.id === spaceId);
          toast.success(
            result.is_active
              ? t('spaces.toggle_activated', { name: space?.name })
              : t('spaces.toggle_deactivated', { name: space?.name })
          );
        }
      } catch {
        // Toggle failure is visible via optimistic revert in useSpaces
      }
    },
    [toggleSpace, spaces, t]
  );

  return (
    <FeatureErrorBoundary feature="rag-spaces">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{t('spaces.title')}</h1>
            <p className="mt-2 text-muted-foreground">{t('spaces.subtitle')}</p>
          </div>
          <Button onClick={() => setCreateOpen(true)} className="sm:w-auto">
            <Plus className="h-4 w-4 mr-2" />
            {t('spaces.create_button')}
          </Button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-40 rounded-lg border bg-muted/50 animate-pulse" />
            ))}
          </div>
        ) : spaces.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <Library className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
            <h3 className="text-lg font-semibold mb-2">{t('spaces.empty_title')}</h3>
            <p className="text-sm text-muted-foreground mb-4">{t('spaces.empty_description')}</p>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              {t('spaces.create_button')}
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {spaces.map((space) => (
              <SpaceCard
                key={space.id}
                space={space}
                onClick={() => router.push(`/dashboard/spaces/${space.id}`)}
                onEdit={() => setEditSpace(space)}
                onDelete={() => setDeleteConfirmSpace(space)}
                onToggle={() => handleToggle(space.id)}
                toggling={toggling}
              />
            ))}
          </div>
        )}

        {/* Dialogs */}
        <CreateSpaceDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onSubmit={handleCreate}
          isLoading={creating}
        />

        <EditSpaceDialog
          open={!!editSpace}
          onOpenChange={(open) => !open && setEditSpace(null)}
          space={editSpace}
          onSubmit={handleUpdate}
          isLoading={updating}
        />

        <DeleteSpaceConfirm
          open={!!deleteConfirmSpace}
          onOpenChange={(open) => !open && setDeleteConfirmSpace(null)}
          spaceName={deleteConfirmSpace?.name || ''}
          onConfirm={handleDelete}
        />
      </div>
    </FeatureErrorBoundary>
  );
}
