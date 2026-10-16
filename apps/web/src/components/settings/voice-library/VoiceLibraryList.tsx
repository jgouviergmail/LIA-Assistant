'use client';

/**
 * The account's own Fish Audio voices (ADR-345): what each is, which slots
 * speak with it, and the two acts a row offers — rename, delete. A voice a
 * slot speaks with is never deleted: the row says why instead of asking, and
 * the API refuses it again if a slot took it meanwhile.
 */

import { type FormEvent, useId, useState } from 'react';
import type { TFunction } from 'i18next';
import { AudioLines, Library, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { RowActions } from '@/components/ui/row-actions';
import { useConfirm } from '@/components/ui/use-confirm';
import { type Language, languageNames } from '@/i18n/settings';
import { lifecycleTone } from '@/lib/status-tone';
import type { LibraryVoice } from '@/types/voice-library';

import { joinedList, libraryRefusal, slotsSentence } from './wording';

const KEY = 'settings.admin.voiceLibrary.list';
const STATES: ReadonlySet<string> = new Set(['created', 'training', 'trained', 'failed']);

function languageLabel(code: string): string {
  return Object.hasOwn(languageNames, code) ? languageNames[code as Language].native : code;
}

interface RowProps {
  voice: LibraryVoice;
  locale: string;
  t: TFunction;
  onRename: (voice: LibraryVoice) => void;
  onDelete: (voice: LibraryVoice) => void;
}

function VoiceRow({ voice, locale, t, onRename, onDelete }: RowProps) {
  const inUse = voice.used_by_slots.length > 0;
  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-border bg-background p-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="break-words text-sm font-medium">{voice.title}</span>
          <Badge variant={lifecycleTone(voice.state)}>
            {t(`${KEY}.states.${STATES.has(voice.state) ? voice.state : 'unknown'}`)}
          </Badge>
        </div>
        {voice.languages.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {joinedList(voice.languages.map(languageLabel), locale)}
          </p>
        )}
        {inUse && (
          <p className="text-xs text-muted-foreground">
            {t(`${KEY}.usedBy`, { slots: slotsSentence(voice.used_by_slots, t, locale) })}
          </p>
        )}
      </div>
      <RowActions
        menuLabel={t(`${KEY}.actions`, { title: voice.title })}
        actions={[
          {
            key: 'rename',
            label: t(`${KEY}.rename`),
            icon: Pencil,
            onSelect: () => onRename(voice),
          },
          {
            key: 'delete',
            label: t(`${KEY}.delete`),
            icon: Trash2,
            tone: 'destructive',
            blocked: inUse,
            onSelect: () => onDelete(voice),
          },
        ]}
      />
    </li>
  );
}

interface RenameDialogProps {
  voice: LibraryVoice;
  maxChars: number;
  locale: string;
  t: TFunction;
  onClose: () => void;
  onRename: (voiceId: string, title: string) => Promise<void>;
}

function RenameDialog({ voice, maxChars, locale, t, onClose, onRename }: RenameDialogProps) {
  const [title, setTitle] = useState(voice.title);
  const [saving, setSaving] = useState(false);
  const words = title.trim();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    // The guard, not the attribute, prevents a double submit (apps/web/CLAUDE.md).
    if (saving || !words) return;
    setSaving(true);
    try {
      await onRename(voice.voice_id, words);
      toast.success(t(`${KEY}.renamed`));
      onClose();
    } catch (error) {
      toast.error(libraryRefusal(error, t, locale));
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t(`${KEY}.renameTitle`)}</DialogTitle>
            <DialogDescription>{t(`${KEY}.renameDescription`)}</DialogDescription>
          </DialogHeader>
          <Input
            label={t(`${KEY}.renameLabel`)}
            value={title}
            maxLength={maxChars}
            onChange={event => setTitle(event.target.value)}
            autoFocus
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" isLoading={saving} aria-disabled={!words || saving}>
              {t(`${KEY}.renameSave`)}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export interface VoiceLibraryListProps {
  voices: LibraryVoice[];
  titleMaxChars: number;
  /** The Intl locale a list of slots is joined in. */
  locale: string;
  t: TFunction;
  onRename: (voiceId: string, title: string) => Promise<void>;
  onRemove: (voiceId: string) => Promise<void>;
}

export function VoiceLibraryList({
  voices,
  titleMaxChars,
  locale,
  t,
  onRename,
  onRemove,
}: VoiceLibraryListProps) {
  const headingId = useId();
  const [renaming, setRenaming] = useState<LibraryVoice | null>(null);
  const { confirm, confirmDialog } = useConfirm();

  const remove = async (voice: LibraryVoice) => {
    if (voice.used_by_slots.length > 0) {
      toast.error(t(`${KEY}.inUse`, { slots: slotsSentence(voice.used_by_slots, t, locale) }));
      return;
    }
    const confirmed = await confirm({
      title: t(`${KEY}.deleteTitle`, { title: voice.title }),
      description: t(`${KEY}.deleteDescription`),
      confirmLabel: t(`${KEY}.deleteConfirm`),
    });
    if (!confirmed) return;
    try {
      await onRemove(voice.voice_id);
      toast.success(t(`${KEY}.deleted`, { title: voice.title }));
    } catch (error) {
      toast.error(libraryRefusal(error, t, locale));
    }
  };

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h3 id={headingId} className="flex items-center gap-2 text-sm font-medium text-foreground">
        <Library className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${KEY}.title`)}
      </h3>
      {voices.length === 0 ? (
        <EmptyState icon={AudioLines} description={t(`${KEY}.empty`)} />
      ) : (
        <ul className="space-y-2">
          {voices.map(voice => (
            <VoiceRow
              key={voice.voice_id}
              voice={voice}
              locale={locale}
              t={t}
              onRename={setRenaming}
              onDelete={target => void remove(target)}
            />
          ))}
        </ul>
      )}
      {renaming && (
        <RenameDialog
          key={renaming.voice_id}
          voice={renaming}
          maxChars={titleMaxChars}
          locale={locale}
          t={t}
          onClose={() => setRenaming(null)}
          onRename={onRename}
        />
      )}
      {confirmDialog}
    </section>
  );
}
