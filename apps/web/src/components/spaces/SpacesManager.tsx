'use client';

/**
 * SpacesManager — the ONE management screen of the knowledge spaces.
 *
 * It is mounted by two doors: the `/dashboard/spaces` page and the settings
 * section « Knowledge spaces ». The settings section used to render an
 * intermediate list (a switch per space and a link to the page) that the
 * owner found useless (2026-10-03): the section now IS the screen, and a
 * single implementation serves both, so the two can never drift.
 *
 * The `variant` only decides the chrome around the grid:
 * - `page`: the route's H1 and subtitle beside the create button, and the
 *   page's three-column grid on wide screens;
 * - `section`: the settings card already carries the title, so the create
 *   button sits alone on the section's toolbar and the grid stops at two
 *   columns (the settings pane is narrower than a page).
 *
 * A card opens the space's detail at `/dashboard/spaces/{id}`; activation,
 * rename and deletion are on the card itself.
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Library, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { FeatureErrorBoundary } from '@/components/errors';
import { SectionToolbar } from '@/components/settings/SectionToolbar';
import { CreateSpaceDialog } from '@/components/spaces/CreateSpaceDialog';
import { DeleteSpaceConfirm } from '@/components/spaces/DeleteSpaceConfirm';
import { EditSpaceDialog } from '@/components/spaces/EditSpaceDialog';
import { SpaceCard } from '@/components/spaces/SpaceCard';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useSpaces } from '@/hooks/useSpaces';
import { cn } from '@/lib/utils';
import type { RAGSpace } from '@/types/rag-spaces';

export interface SpacesManagerProps {
  /** Which door mounted the screen: the standalone page or the settings card. */
  variant: 'page' | 'section';
}

const GRID_CLASSES: Record<SpacesManagerProps['variant'], string> = {
  page: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  section: 'grid-cols-1 md:grid-cols-2',
};

export function SpacesManager({ variant }: SpacesManagerProps) {
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
          const space = spaces.find(s => s.id === spaceId);
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

  const openCreate = () => setCreateOpen(true);
  const grid = cn('grid gap-4', GRID_CLASSES[variant]);

  return (
    <FeatureErrorBoundary feature="rag-spaces">
      <div className={variant === 'page' ? 'space-y-6' : 'space-y-4'}>
        {variant === 'page' ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{t('spaces.title')}</h1>
              <p className="mt-2 text-muted-foreground">{t('spaces.subtitle')}</p>
            </div>
            <Button onClick={openCreate} className="sm:w-auto">
              <Plus className="h-4 w-4 mr-2" />
              {t('spaces.create_button')}
            </Button>
          </div>
        ) : (
          // The settings card already names the section: no second title,
          // only the section's own action bar (ADR-207: a labelled, solid CTA).
          spaces.length > 0 && (
            <SectionToolbar
              count=""
              menuLabel={t('common.more_actions')}
              primary={{
                key: 'create',
                label: t('spaces.create_button'),
                icon: Plus,
                onSelect: openCreate,
              }}
            />
          )
        )}

        {loading ? (
          <div className={grid}>
            {[1, 2, 3].map(i => (
              <div key={i} className="h-40 rounded-lg border bg-muted/50 animate-pulse" />
            ))}
          </div>
        ) : spaces.length === 0 ? (
          <EmptyState
            // A whole route says "empty" at page scale; inside the settings
            // card the section-scale state keeps the card's proportions.
            variant={variant}
            icon={Library}
            title={t('spaces.empty_title')}
            description={t('spaces.empty_description')}
            action={{
              label: t('spaces.create_button'),
              onClick: openCreate,
              icon: Plus,
            }}
          />
        ) : (
          <div className={grid}>
            {spaces.map(space => (
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

        <CreateSpaceDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onSubmit={handleCreate}
          isLoading={creating}
        />

        <EditSpaceDialog
          open={!!editSpace}
          onOpenChange={open => !open && setEditSpace(null)}
          space={editSpace}
          onSubmit={handleUpdate}
          isLoading={updating}
        />

        <DeleteSpaceConfirm
          open={!!deleteConfirmSpace}
          onOpenChange={open => !open && setDeleteConfirmSpace(null)}
          spaceName={deleteConfirmSpace?.name || ''}
          onConfirm={handleDelete}
        />
      </div>
    </FeatureErrorBoundary>
  );
}
