'use client';

/**
 * CardAssist — a business card photographed into a new contact (ADR-372).
 *
 * One icon in the editor's title line: a phone opens its camera, a computer its files. The picture
 * is read by the server, redrawn first, and fills the form under the person's eyes: nothing exists
 * until they save it. What it cost stands in a toast, the form keeping all its room.
 */
import { useRef, useState, type ChangeEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { ASSIST_PATHS, type CardAnswer, type ProposedContact } from '@/lib/workbench/assist';
import { workbenchRefusal } from '@/lib/workbench/errors';

import { useAssistBounds } from '../WorkbenchShell';
import { AssistStars } from './AssistStars';
import { tellCost } from './tellings';

const BYTES_PER_MEGABYTE = 1024 * 1024;

export interface CardAssistProps {
  lng: Language;
  /** The published ceiling of a picture. */
  maxBytes: number;
  onRead: (card: ProposedContact) => void;
}

export function CardAssist({ lng, maxBytes, onRead }: CardAssistProps) {
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const { mutate } = useApiMutation<FormData, CardAnswer>({
    method: 'POST',
    componentName: 'ContactCard',
  });
  if (!bounds) return null;
  const label = t('workbench.assist.contacts.from_card');

  const picked = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Emptied at once: the same picture picked again is a new choice, not no change.
    event.target.value = '';
    if (!file) return;
    if (file.size > maxBytes) {
      toast.error(
        t('workbench.errors.too_large_bounded', {
          megabytes: Number((maxBytes / BYTES_PER_MEGABYTE).toFixed(1)),
        })
      );
      return;
    }
    const form = new FormData();
    form.append('file', file);
    setBusy(true);
    try {
      const answer = await mutate(ASSIST_PATHS.contactFromCard, form);
      if (!answer) throw new Error('contact_card_unread');
      tellCost(answer.usage);
      onRead(answer.contact);
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.assist.failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <input
        ref={input}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={event => void picked(event)}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        isLoading={busy}
        aria-label={label}
        title={label}
        onClick={() => input.current?.click()}
      >
        <AssistStars className="h-4 w-4" aria-hidden="true" />
      </Button>
    </>
  );
}
