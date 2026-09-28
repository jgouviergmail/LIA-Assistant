'use client';

/**
 * The sites the listener adds to their newsroom (ADR-324 decision 38). Each one
 * is ticked while the radio reads it — unticked, it is paused: not read, not
 * offered, and kept — can be renamed and removed, and says what it holds for the
 * listener and whether its last readings failed.
 *
 * A site is CHECKED first — the API looks for the feed it serves and describes
 * it (title, entries), or says why there is none — and only then added; the API
 * looks again when adding, since what is sent is the address, never a feed URL
 * the page was handed.
 *
 * The check button keeps its focus while it works (`aria-disabled` and a guard,
 * never `disabled` on the control just activated — apps/web CLAUDE.md).
 */
import { Globe, Pencil, Trash2 } from 'lucide-react';
import { type FormEvent, useRef, useState } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import type { UseRadioSourcesReturn } from '@/hooks/useRadioSources';
import { useTranslation } from '@/i18n/client';
import { sourceLanguageName } from '@/lib/radio/articles';
import { sayRefusal } from '@/lib/radio/errors';
import { speakableName } from '@/lib/radio/preferences';
import type { RadioCustomSource, RadioDiscovery } from '@/lib/radio/types';
import type { BaseSettingsProps } from '@/types/settings';

import { RadioSourceLogo } from './RadioSourceLogo';

interface RadioCustomSourcesProps {
  lng: BaseSettingsProps['lng'];
  newsroom: UseRadioSourcesReturn;
  /** How many sites a listener may add (published). */
  max: number;
  /** The longest address the API accepts (published). */
  addressMax: number;
  /** The longest name a site may be given (published). */
  titleMax: number;
}

export function RadioCustomSources({
  lng,
  newsroom,
  max,
  addressMax,
  titleMax,
}: RadioCustomSourcesProps) {
  const { t } = useTranslation(lng);
  const { sources, preview, add, remove, change, busy } = newsroom;
  const [address, setAddress] = useState('');
  const [found, setFound] = useState<RadioDiscovery | null>(null);
  const [renaming, setRenaming] = useState<RadioCustomSource | null>(null);
  const own = sources?.own ?? null;
  const room = (own?.length ?? 0) < max;

  const check = async (event: FormEvent) => {
    event.preventDefault();
    const typed = address.trim();
    if (busy || !typed) return;
    const result = await preview(typed);
    if (!result.ok) {
      toast.error(sayRefusal(t, result.refusal, 'radio.settings.sites.check_failed'));
    }
    setFound(result.ok ? result.value : null);
  };
  const confirm = async () => {
    if (busy || found?.outcome !== 'found') return;
    const added = await add(address.trim());
    if (!added.ok) {
      toast.error(sayRefusal(t, added.refusal, 'radio.settings.sites.add_failed'));
      return;
    }
    setAddress('');
    setFound(null);
  };
  const drop = async (source: RadioCustomSource) => {
    if (!(await remove(source.id))) toast.error(t('radio.settings.sites.remove_failed'));
  };
  const pause = async (source: RadioCustomSource, running: boolean) => {
    if (!(await change(source.id, { paused: !running }))) {
      toast.error(t('radio.settings.sites.change_failed'));
    }
  };
  const rename = async (source: RadioCustomSource, title: string) => {
    if (await change(source.id, { title })) setRenaming(null);
    else toast.error(t('radio.settings.sites.change_failed'));
  };

  return (
    <div className="space-y-3">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Globe className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('radio.settings.sites.title')}
      </h4>
      <p className="text-xs text-muted-foreground">
        {t('radio.settings.sites.hint', { count: max })}
      </p>
      <SourceList
        lng={lng}
        sources={own}
        onRemove={drop}
        onRename={setRenaming}
        onRunning={pause}
      />
      {room && (
        <form onSubmit={check} className="flex items-end gap-2" aria-busy={busy}>
          <div className="min-w-0 flex-1">
            <Input
              label={t('radio.settings.sites.address')}
              value={address}
              maxLength={addressMax}
              onChange={event => {
                setAddress(event.target.value);
                setFound(null);
              }}
            />
          </div>
          <Button type="submit" variant="outline" aria-disabled={busy || undefined}>
            {t('radio.settings.sites.check')}
          </Button>
        </form>
      )}
      <p className="sr-only" role="status">
        {busy ? t('radio.settings.sites.checking') : ''}
      </p>
      {found && <Discovered lng={lng} found={found} onAdd={confirm} busy={busy} />}
      {renaming && (
        <RenameDialog
          lng={lng}
          source={renaming}
          max={titleMax}
          busy={busy}
          onCancel={() => setRenaming(null)}
          onSave={title => void rename(renaming, title)}
        />
      )}
    </div>
  );
}

function SourceList({
  lng,
  sources,
  onRemove,
  onRename,
  onRunning,
}: {
  lng: BaseSettingsProps['lng'];
  sources: RadioCustomSource[] | null;
  onRemove: (source: RadioCustomSource) => void;
  onRename: (source: RadioCustomSource) => void;
  onRunning: (source: RadioCustomSource, running: boolean) => void;
}) {
  const { t } = useTranslation(lng);
  if (sources === null) return null;
  if (sources.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('radio.settings.sites.empty')}</p>;
  }
  return (
    <ul className="space-y-2">
      {sources.map(source => {
        const name = source.title || source.feed_url;
        const id = `radio-site-${source.id}`;
        const hintId = `${id}-hint`;
        return (
          <li
            key={source.id}
            className="flex items-stretch justify-between gap-3 rounded-md border p-2"
          >
            <div className="flex min-w-0 items-stretch gap-2">
              <Checkbox
                id={id}
                className="self-center"
                aria-describedby={hintId}
                checked={!source.paused}
                onChange={event => onRunning(source, event.target.checked)}
              />
              <RadioSourceLogo url={source.feed_url} />
              <div className="min-w-0 space-y-0.5">
                <Label htmlFor={id} className="break-words" title={source.feed_url}>
                  {source.language
                    ? t('radio.settings.news.with_language', {
                        name,
                        language: sourceLanguageName(source.language, lng),
                      })
                    : name}
                </Label>
                <div
                  id={hintId}
                  className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
                >
                  <span>
                    {source.paused
                      ? t('radio.settings.sites.paused')
                      : t('radio.settings.news.counts', {
                          stories: source.stories,
                          unheard: source.unheard,
                        })}
                  </span>
                  {source.failing && (
                    <Badge variant="warning" size="sm">
                      {t('radio.settings.news.failing')}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <RowActions
              className="self-center"
              menuLabel={t('common.actions_for', { name })}
              actions={[
                {
                  key: 'rename',
                  label: t('radio.settings.sites.rename', { title: name }),
                  icon: Pencil,
                  onSelect: () => onRename(source),
                },
                {
                  key: 'remove',
                  label: t('radio.settings.sites.remove', { title: name }),
                  icon: Trash2,
                  tone: 'destructive',
                  onSelect: () => onRemove(source),
                },
              ]}
            />
          </li>
        );
      })}
    </ul>
  );
}

/**
 * A new name for a site, folded as the API folds it; an empty one saves nothing.
 *
 * Radix hands the focus back to a dialog's Trigger, and this one has none (the row's
 * actions open it): it remembers who had the focus and gives it back when it closes.
 */
function RenameDialog({
  lng,
  source,
  max,
  busy,
  onCancel,
  onSave,
}: {
  lng: BaseSettingsProps['lng'];
  source: RadioCustomSource;
  max: number;
  busy: boolean;
  onCancel: () => void;
  onSave: (title: string) => void;
}) {
  const { t } = useTranslation(lng);
  const [draft, setDraft] = useState(source.title);
  const returnFocus = useRef<HTMLElement | null>(null);
  const name = speakableName(draft, max);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (busy || name === '') return;
    onSave(name);
  };
  return (
    <Dialog open onOpenChange={open => (open ? undefined : onCancel())}>
      <DialogContent
        onOpenAutoFocus={() => {
          const active = document.activeElement;
          returnFocus.current = active instanceof HTMLElement ? active : null;
        }}
        onCloseAutoFocus={event => {
          // A « ⋮ » menu's item is gone by now: its menu already gave the focus back.
          if (!returnFocus.current?.isConnected) return;
          event.preventDefault();
          returnFocus.current.focus();
        }}
      >
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t('radio.settings.sites.rename_title')}</DialogTitle>
            <DialogDescription>{source.feed_url}</DialogDescription>
          </DialogHeader>
          <Input
            label={t('radio.settings.sites.rename_label')}
            value={draft}
            maxLength={max}
            onChange={event => setDraft(event.target.value)}
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancel}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" aria-disabled={busy || name === '' || undefined}>
              {t('radio.settings.sites.rename_save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Discovered({
  lng,
  found,
  onAdd,
  busy,
}: {
  lng: BaseSettingsProps['lng'];
  found: RadioDiscovery;
  onAdd: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation(lng);
  if (found.outcome !== 'found') {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t(`radio.settings.sites.outcome.${found.outcome}`)}
      </p>
    );
  }
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-card p-3">
      <p className="min-w-0 text-sm">
        {t('radio.settings.sites.found', {
          title: found.title || found.feed_url,
          count: found.entries ?? 0,
        })}
      </p>
      <Button type="button" onClick={onAdd} aria-disabled={busy || undefined}>
        {t('radio.settings.sites.add')}
      </Button>
    </div>
  );
}
