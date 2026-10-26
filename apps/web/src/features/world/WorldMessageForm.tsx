'use client';

import { useId } from 'react';
import { Info, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { publicMessageText, PUBLIC_MESSAGE_CHARS } from './public-message-protocol';
import { messageText } from './message-protocol';
import type { WorldParticipant } from './useWorldSession';

export function WorldMessageForm({
  lng,
  publicMode = false,
  participants,
  draft,
  recipient,
  recipientAlias,
  consent,
  enabled,
  busy,
  onDraft,
  onConsent,
  onSubmit,
}: {
  lng: Language;
  publicMode?: boolean;
  participants: WorldParticipant[];
  draft: string;
  recipient: string;
  recipientAlias?: string;
  consent: boolean;
  enabled: boolean;
  busy: boolean;
  onDraft(value: string): void;
  onConsent(value: boolean): void;
  onSubmit(): void;
}) {
  const { t } = useTranslation(lng);
  const field = useId();
  const known = publicMode || participants.some(person => person.id === recipient);
  const valid = publicMode ? publicMessageText(draft) : messageText(draft);
  const maximum = publicMode ? PUBLIC_MESSAGE_CHARS : 1000;
  const canSubmit = enabled && !busy && known && consent && valid !== null;
  return (
    <form
      className="world-message-composer flex min-h-0 shrink-0 flex-col gap-2 overflow-y-auto"
      aria-busy={busy}
      aria-label={
        publicMode ? t('world.public.compose') : t('world.messages.to', { name: recipientAlias })
      }
      onSubmit={event => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
    >
      {recipient && !known && (
        <p role="status" className="text-xs text-muted-foreground">
          {t('world.messages.left')}
        </p>
      )}
      <div className="flex min-h-0 items-end gap-2">
        <div className="min-w-0 flex-1">
          <Textarea
            name="world-message"
            aria-label={t('world.messages.message')}
            className="h-16 max-h-28 min-h-16 resize-none"
            value={draft}
            onChange={event => {
              if (!busy) onDraft(event.target.value);
            }}
            readOnly={busy}
            maxLength={maximum * 2}
            autoComplete="off"
            placeholder={t('world.messages.placeholder')}
            error={draft.trim() && valid === null ? t('world.messages.invalid') : undefined}
            onKeyDown={event => {
              if (
                canSubmit &&
                event.key === 'Enter' &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing &&
                window.matchMedia('(pointer:fine)').matches
              ) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
        </div>
        <Button
          type="submit"
          size="icon"
          className="mb-0.5 min-h-11 min-w-11 shrink-0"
          aria-disabled={!canSubmit}
          aria-label={t('world.messages.send')}
        >
          <Send className="size-4" aria-hidden="true" />
        </Button>
      </div>
      <div className="flex items-center gap-1">
        <label
          htmlFor={field + '-consent'}
          className="flex min-h-11 min-w-0 flex-1 items-center gap-2 text-xs"
        >
          <input
            id={field + '-consent'}
            aria-label={t('world.messages.consent')}
            type="checkbox"
            name="world-translation-consent"
            className="size-5 shrink-0 accent-primary"
            checked={consent}
            onChange={event => {
              if (!busy) onConsent(event.target.checked);
            }}
            aria-disabled={busy}
          />
          {t('world.messages.translation_consent_short')}
        </label>
        <Dialog>
          <DialogTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="min-h-11 min-w-11"
              aria-label={t('world.messages.translation_details')}
            >
              <Info className="size-4" aria-hidden="true" />
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Info className="size-5 text-primary" aria-hidden="true" />
                {t('world.messages.translation_details')}
              </DialogTitle>
              <DialogDescription>
                {t(publicMode ? 'world.public.translation_details' : 'world.messages.consent')}
              </DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>
        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
          {Array.from(draft).length}/{maximum}
        </span>
      </div>
    </form>
  );
}
