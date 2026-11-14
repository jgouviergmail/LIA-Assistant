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

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Library, Plus } from '@/lib/icons';
import { toast } from 'sonner';

import { FeatureErrorBoundary } from '@/components/errors';
import { SectionToolbar } from '@/components/settings/SectionToolbar';
import { CreateSpaceDialog } from '@/components/spaces/CreateSpaceDialog';
import { DeleteSpaceConfirm } from '@/components/spaces/DeleteSpaceConfirm';
import { EditSpaceDialog } from '@/components/spaces/EditSpaceDialog';
import { SpaceCard } from '@/components/spaces/SpaceCard';
import { SpaceCardList } from '@/components/spaces/SpaceCardList';
import { SpaceListToolbar } from '@/components/spaces/SpaceListToolbar';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { SectionHeader } from '@/components/ui/section-header';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useSpaces } from '@/hooks/useSpaces';
import { useAuth } from '@/hooks/useAuth';
import { useDebounce } from '@/hooks/useDebounce';
import { SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { cn } from '@/lib/utils';
import type { RAGSpace, SpaceListQuery } from '@/types/rag-spaces';

export interface SpacesManagerProps {
  /** Which door mounted the screen: the standalone page or the settings card. */
  variant: 'page' | 'section';
}

const GRID_CLASSES: Record<SpacesManagerProps['variant'], string> = {
  page: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  section: 'grid-cols-1 md:grid-cols-2',
};

export function SpacesManager({ variant }: SpacesManagerProps) {
  const { user } = useAuth();
  return <SpaceList key={user?.id ?? 'anonymous'} variant={variant} />;
}

function SpaceListHeader({ variant, onCreate }: SpacesManagerProps & { onCreate: () => void }) {
  const { t } = useTranslation();
  if (variant === 'page') {
    return (
      <SectionHeader
        level={1}
        icon={Library}
        title={t('spaces.title')}
        description={t('spaces.subtitle')}
        actions={
          <Button onClick={onCreate}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('spaces.create_button')}
          </Button>
        }
      />
    );
  }
  return (
    <SectionToolbar
      count=""
      menuLabel={t('common.more_actions')}
      primary={{ key: 'create', label: t('spaces.create_button'), icon: Plus, onSelect: onCreate }}
    />
  );
}

function SpaceList({ variant }: SpacesManagerProps) {
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const [criteria, setCriteria] = useState<SpaceListQuery>({ q: '', field: 'name', sort: 'name' });
  const query = useDebounce(criteria.q, SEARCH_DEBOUNCE_MS);
  const [onlyManaged, setOnlyManaged] = useState(false);
  const filtering = Boolean(query.trim() || onlyManaged);
  const {
    spaces,
    loading,
    error,
    refetch,
    createSpace,
    updateSpace,
    deleteSpace,
    toggleSpace,
    creating,
    updating,
    toggling,
  } = useSpaces({ ...criteria, q: query });

  const [createOpen, setCreateOpen] = useState(false);
  const [editSpace, setEditSpace] = useState<RAGSpace | null>(null);
  const [deleteConfirmSpace, setDeleteConfirmSpace] = useState<RAGSpace | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const favoriteFocus = useRef<string | null>(null);
  const visible = onlyManaged ? spaces.filter(space => space.kind != null) : spaces;

  // Moving between bands remounts the star: restore keyboard focus after the
  // confirmed list refresh, including an unsuccessful preference write.
  useEffect(() => {
    if (loading || updating || !favoriteFocus.current) return;
    const button = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>('[data-space-favorite]') ?? []
    ).find(candidate => candidate.dataset.spaceFavorite === favoriteFocus.current);
    if (button) {
      button.focus({ preventScroll: true });
      favoriteFocus.current = null;
    }
  }, [loading, updating, spaces]);

  const handleFavorite = async (space: RAGSpace) => {
    favoriteFocus.current = space.id;
    try {
      await updateSpace(space.id, { is_favorite: !space.is_favorite });
    } catch {
      toast.error(t('spaces.favorite_error'));
    }
  };

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
      <div ref={listRef} className={variant === 'page' ? 'space-y-6' : 'space-y-4'}>
        <SpaceListHeader variant={variant} onCreate={openCreate} />

        <SpaceListToolbar
          value={criteria}
          onChange={setCriteria}
          onlyManaged={onlyManaged}
          onToggleManaged={() => setOnlyManaged(value => !value)}
          surface={variant === 'page' ? 'primary' : 'nested'}
        />

        {error ? (
          <div role="alert" className="space-y-2">
            <p>{t('spaces.list.load_error')}</p>
            <Button
              variant="outline"
              onClick={() => {
                void refetch().catch(() => {});
              }}
            >
              {t('common.retry')}
            </Button>
          </div>
        ) : loading ? (
          <div className={grid}>
            {[1, 2, 3].map(i => (
              <div key={i} className="h-40 rounded-lg border bg-muted/50 animate-pulse" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            // Creation remains in the page header, including an empty collection.
            variant="section"
            reason={filtering ? 'no-match' : 'no-data'}
            icon={Library}
            title={t(filtering ? 'spaces.list.no_matches' : 'spaces.empty_title')}
            description={t(filtering ? 'spaces.list.no_matches_hint' : 'spaces.empty_description')}
            action={
              filtering
                ? {
                    label: t('spaces.list.clear'),
                    onClick: () => {
                      setCriteria(current => ({ ...current, q: '' }));
                      setOnlyManaged(false);
                    },
                  }
                : undefined
            }
          />
        ) : (
          <SpaceCardList spaces={visible} gridClassName={grid}>
            {space => (
              <SpaceCard
                key={space.id}
                surface={variant === 'page' ? 'primary' : 'nested'}
                space={space}
                onClick={() => router.push(`/dashboard/spaces/${space.id}`)}
                onEdit={() => setEditSpace(space)}
                onDelete={() => setDeleteConfirmSpace(space)}
                onToggle={() => handleToggle(space.id)}
                onToggleFavorite={() => void handleFavorite(space)}
                favoriting={updating}
                toggling={toggling}
              />
            )}
          </SpaceCardList>
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
