'use client';

/**
 * The skill library (ADR-327): find a skill on a portal or at a GitHub address,
 * read it before installing it, keep it up to date.
 *
 * Mounted only while open (the parent decides), so every opening starts from
 * the tab it was asked for. The three tabs stay mounted under whatever the
 * dialog shows over them — a search and its results survive a look at a skill.
 * Every act goes through `lib/skill-library/dialog-state.ts`; a refusal is the
 * sentence the API named, shown where the reader is.
 */
import { useReducer, useState } from 'react';
import { Library } from 'lucide-react';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useLibraryActions } from '@/hooks/useSkillLibrary';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  initialLibraryState,
  isLibraryTab,
  libraryDialogReducer,
  type LibraryTab,
} from '@/lib/skill-library/dialog-state';
import { libraryRefusalOf, type LibraryRefusal } from '@/lib/skill-library/errors';
import { installRequestOf } from '@/lib/skill-library/types';
import type { LibraryInstalledItem, LibrarySearchItem } from '@/lib/skill-library/types';

import { LibraryAddressTab } from './LibraryAddressTab';
import { LibraryFolderChoice } from './LibraryFolderChoice';
import { LibraryInstalledTab } from './LibraryInstalledTab';
import { LibraryPreviewPanel } from './LibraryPreviewPanel';
import { LibrarySearchTab } from './LibrarySearchTab';

const GENERIC: LibraryRefusal = { key: 'settings.skills.library.errors.generic' };

export function SkillLibraryDialog({
  lng,
  initialTab = 'search',
  onOpenChange,
  onChanged,
}: {
  lng: Language;
  initialTab?: LibraryTab;
  onOpenChange: (open: boolean) => void;
  /** Called after an install or an update, so the gallery reads its skills again. */
  onChanged: () => void;
}) {
  const { t } = useTranslation(lng);
  const actions = useLibraryActions();
  const [state, dispatch] = useReducer(libraryDialogReducer, initialTab, initialLibraryState);
  const busy = state.busy !== null;
  // Moves after every install or update, so the search reads its marks again.
  const [revision, setRevision] = useState(0);

  const refuse = (error: unknown) =>
    dispatch({ type: 'refused', refusal: libraryRefusalOf(error, lng) ?? GENERIC });

  const read = async (query: Parameters<typeof actions.preview>[0], skillId: string | null) => {
    if (busy) return;
    dispatch({ type: 'busy', busy: 'reading' });
    try {
      dispatch({ type: 'read', answer: await actions.preview(query), skillId });
    } catch (error) {
      refuse(error);
    }
  };

  const readItem = (item: LibrarySearchItem, portal: string) =>
    void read(
      {
        repository: item.repository ?? undefined,
        skill_id: item.skill_id,
        portal,
        registry_id: item.registry_id,
      },
      item.skill_id
    );

  const review = async (item: LibraryInstalledItem) => {
    if (busy) return;
    dispatch({ type: 'busy', busy: 'reading' });
    try {
      dispatch({
        type: 'update_read',
        skill: item,
        update: await actions.updatePreview(item.skill_id),
      });
    } catch (error) {
      refuse(error);
    }
  };

  const confirm = async () => {
    const view = state.view;
    if (busy || (view.kind !== 'preview' && view.kind !== 'update')) return;
    dispatch({ type: 'busy', busy: 'installing' });
    try {
      const done =
        view.kind === 'preview'
          ? await actions.install(installRequestOf(view.preview, view.skillId))
          : await actions.update(view.skill.skill_id, view.update.preview.commit_sha);
      toast.success(
        t(
          view.kind === 'preview'
            ? 'settings.skills.library.install_success'
            : 'settings.skills.library.update_success',
          { name: done.name }
        )
      );
      onChanged();
      setRevision(value => value + 1);
      dispatch({ type: 'done', tab: view.kind === 'preview' ? state.tab : 'installed' });
    } catch (error) {
      refuse(error);
    }
  };

  const view = state.view;
  const refusal = state.refusal;
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Library className="h-5 w-5 text-primary" aria-hidden />
            {t('settings.skills.library.title')}
          </DialogTitle>
          <DialogDescription>{t('settings.skills.library.description')}</DialogDescription>
        </DialogHeader>

        {refusal && (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm"
          >
            {t(refusal.key, {
              ...refusal.values,
              ...(refusal.risk ? { risk: t(`settings.skills.library.risk.${refusal.risk}`) } : {}),
            })}
          </p>
        )}

        <div hidden={view.kind !== 'browse'}>
          <Tabs
            value={state.tab}
            onValueChange={value => {
              if (isLibraryTab(value)) dispatch({ type: 'tab', tab: value });
            }}
          >
            <TabsList className="grid h-auto w-full grid-cols-3">
              <TabsTrigger
                className="h-auto min-h-7 whitespace-normal px-2 text-center leading-tight"
                value="search"
              >
                {t('settings.skills.library.tabs.search')}
              </TabsTrigger>
              <TabsTrigger
                className="h-auto min-h-7 whitespace-normal px-2 text-center leading-tight"
                value="address"
              >
                {t('settings.skills.library.tabs.address')}
              </TabsTrigger>
              <TabsTrigger
                className="h-auto min-h-7 whitespace-normal px-2 text-center leading-tight"
                value="installed"
              >
                {t('settings.skills.library.tabs.installed')}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="search" forceMount hidden={state.tab !== 'search'}>
              <LibrarySearchTab t={t} revision={revision} onRead={readItem} />
            </TabsContent>
            <TabsContent value="address" forceMount hidden={state.tab !== 'address'}>
              <LibraryAddressTab
                t={t}
                busy={state.busy === 'reading'}
                onRead={address => void read({ address }, null)}
              />
            </TabsContent>
            <TabsContent value="installed">
              <LibraryInstalledTab t={t} onReview={item => void review(item)} />
            </TabsContent>
          </Tabs>
        </div>

        {view.kind === 'choosing' && (
          <LibraryFolderChoice
            choice={view.choice}
            busy={busy}
            t={t}
            onPick={path =>
              void read({ repository: view.choice.repository, ref: view.choice.ref, path }, null)
            }
            onBack={() => dispatch({ type: 'back' })}
          />
        )}
        {view.kind === 'preview' && (
          <LibraryPreviewPanel
            preview={view.preview}
            mode="install"
            busy={state.busy === 'installing'}
            t={t}
            onConfirm={() => void confirm()}
            onBack={() => dispatch({ type: 'back' })}
          />
        )}
        {view.kind === 'update' && (
          <LibraryPreviewPanel
            preview={view.update.preview}
            mode="update"
            changes={view.update.changes}
            busy={state.busy === 'installing'}
            t={t}
            onConfirm={() => void confirm()}
            onBack={() => dispatch({ type: 'back' })}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
