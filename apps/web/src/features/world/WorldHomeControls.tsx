'use client';

import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { House, LoaderCircle, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ApiError } from '@/lib/api-client';
import { useWorldHome } from './useWorldHome';
import { previewHome } from './home-preview';
import type { HomeEdit } from './home-protocol';
import type { HomeSkin } from './home-projection';
import { WorldHomeFields } from './WorldHomeFields';
import { returnWorldFocus } from './useWorldConversationDock';
import { useWorldAccountIdentity, WorldPrivateActivity } from './WorldAccountGuard';

interface Draft {
  revision: number;
  edit: HomeEdit;
  reset: boolean;
}
interface Props {
  lng: Language;
  ownerId: string;
  enabled: boolean;
  onSkin(skin: HomeSkin | null): void;
  onEditing(editing: boolean): void;
}

export function WorldHomeControls({ lng, ownerId, enabled, onSkin, onEditing }: Props) {
  const { t } = useTranslation(lng);
  const { verified } = useWorldAccountIdentity();
  const home = useWorldHome(ownerId, enabled);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<'conflict' | 'failed' | null>(null);
  const lifetime = useRef(0);
  const opener = useRef<HTMLButtonElement>(null);
  const value = home.home;
  const editing = draft !== null;
  const skin = useMemo(
    () => (value ? (draft ? previewHome(value, draft.edit) : value.decoration) : null),
    [value, draft]
  );
  useEffect(() => {
    onSkin(skin);
  }, [skin, onSkin]);
  useEffect(() => {
    onEditing(editing);
    return () => onEditing(false);
  }, [editing, onEditing]);
  function close() {
    lifetime.current++;
    setDraft(null);
    setError(null);
  }
  async function save() {
    if (!draft || home.saving || (value?.needs_reset && !draft.reset)) return;
    const turn = lifetime.current;
    try {
      const accepted = await home.save(
        draft.reset
          ? { expected_revision: draft.revision, reset: true }
          : {
              palette: draft.edit.palette,
              expected_revision: draft.revision,
            }
      );
      if (accepted && turn === lifetime.current) close();
    } catch (failure) {
      if (turn === lifetime.current)
        setError(failure instanceof ApiError && failure.status === 409 ? 'conflict' : 'failed');
    }
  }
  return (
    <>
      <HomeButton
        lng={lng}
        buttonRef={opener}
        loading={home.loading}
        failed={home.failed}
        disabled={!enabled || !verified || (!value && home.loading)}
        onClick={() => {
          if (!value || home.failed) {
            void home.refresh();
            return;
          }
          lifetime.current++;
          setError(null);
          setDraft({
            revision: value.preferences.revision,
            reset: false,
            edit: {
              palette: value.preferences.palette,
            },
          });
        }}
      />
      {home.failed && !draft && (
        <span role="status" className="sr-only">
          {t('world.home.failed')}
        </span>
      )}
      <WorldPrivateActivity>
        <Dialog
          modal={false}
          open={!!draft}
          onOpenChange={open => {
            if (!open) close();
          }}
        >
          <DialogContent
            className="world-home-dialog left-auto right-3 top-3 h-[min(48rem,calc(100dvh-1.5rem))] w-[min(26rem,calc(100%-1.5rem))] max-w-none translate-x-0 translate-y-0 grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 max-md:bottom-3 max-md:top-auto max-md:h-[62dvh] max-md:max-h-[62dvh]"
            onInteractOutside={event => event.preventDefault()}
            onCloseAutoFocus={event => {
              returnWorldFocus(event, opener.current);
            }}
          >
            <DialogHeader className="px-6 pb-4 pt-6">
              <DialogTitle className="flex items-center gap-2">
                <House className="size-5 text-primary" aria-hidden="true" />
                {t('world.home.title')}
              </DialogTitle>
              <DialogDescription>{t('world.home.description')}</DialogDescription>
            </DialogHeader>
            {draft && value && (
              <form
                className="flex min-h-0 flex-col"
                aria-busy={home.saving}
                onSubmit={event => {
                  event.preventDefault();
                  void save();
                }}
              >
                <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 pb-4">
                  {value.needs_reset && (
                    <p role="alert" className="text-sm">
                      {t('world.home.needs_reset')}
                    </p>
                  )}
                  <fieldset
                    disabled={value.needs_reset}
                    aria-disabled={home.saving}
                    className="space-y-5"
                  >
                    <WorldHomeFields
                      disabled={value.needs_reset}
                      lng={lng}
                      value={draft.edit}
                      onChange={edit => {
                        if (!home.saving)
                          setDraft(current => (current ? { ...current, edit } : current));
                      }}
                    />
                  </fieldset>
                  <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
                    <ShieldCheck className="size-4 shrink-0" aria-hidden="true" />
                    {t('world.home.private')}
                  </p>
                  {error && (
                    <p role="alert" className="text-sm text-destructive">
                      {t('world.home.' + error)}
                    </p>
                  )}
                  {error === 'conflict' && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        close();
                        void home.refresh();
                      }}
                    >
                      {t('world.home.reload')}
                    </Button>
                  )}
                </div>
                <HomeEditorActions
                  lng={lng}
                  saving={home.saving}
                  needsReset={value.needs_reset}
                  reset={draft.reset}
                  onCancel={close}
                  onReset={() =>
                    setDraft(current =>
                      current
                        ? {
                            ...current,
                            reset: value.needs_reset,
                            edit: { palette: 'auto' },
                          }
                        : current
                    )
                  }
                />
              </form>
            )}
          </DialogContent>
        </Dialog>
      </WorldPrivateActivity>
    </>
  );
}

function HomeEditorActions({
  lng,
  saving,
  needsReset,
  reset,
  onCancel,
  onReset,
}: {
  lng: Language;
  saving: boolean;
  needsReset: boolean;
  reset: boolean;
  onCancel(): void;
  onReset(): void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border bg-background px-6 py-4">
      <Button
        type="submit"
        className="min-h-11"
        disabled={needsReset && !reset}
        aria-disabled={saving}
      >
        {saving && <LoaderCircle className="mr-2 size-4 animate-spin" aria-hidden="true" />}
        {t('world.home.save')}
      </Button>
      <Button type="button" variant="outline" className="min-h-11" onClick={onCancel}>
        {t('world.home.cancel')}
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="min-h-11"
        aria-disabled={saving}
        onClick={() => {
          if (!saving) onReset();
        }}
      >
        {t('world.home.reset')}
      </Button>
    </div>
  );
}

function HomeButton({
  lng,
  loading,
  failed,
  disabled,
  onClick,
  buttonRef,
}: {
  lng: Language;
  loading: boolean;
  failed: boolean;
  disabled: boolean;
  onClick(): void;
  buttonRef: RefObject<HTMLButtonElement | null>;
}) {
  const { t } = useTranslation(lng);
  return (
    <Button
      ref={buttonRef}
      variant="ghost"
      size="sm"
      className="min-h-11 min-w-11"
      disabled={disabled}
      onClick={onClick}
      aria-label={t(failed ? 'world.home.retry' : 'world.home.open')}
      title={failed ? t('world.home.failed') : undefined}
    >
      {loading ? (
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      ) : (
        <House className="size-4" aria-hidden="true" />
      )}
      <span className={failed ? 'hidden text-destructive sm:inline' : 'hidden sm:inline'}>
        {t(failed ? 'world.home.retry' : 'world.home.short')}
      </span>
    </Button>
  );
}
