'use client';

/**
 * ContactPortrait — a contact's photo, or its initials (ADR-369, lot 9).
 *
 * The photo is read through the API as a blob, as a file's preview is: no provider address reaches
 * the page. A contact holding none keeps its initials, without a word. The person changes it or
 * takes it off here; the API redraws whatever is picked. A contact met in mail has none to read.
 */
import { Camera, Trash2 } from '@/lib/icons';
import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { contactInitials, contactName } from '@/lib/workbench/contacts';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchContact } from '@/lib/workbench/types';

const PHOTO_PATH = '/workbench/contacts/photo';
const BYTES_PER_MEGABYTE = 1024 * 1024;

export interface ContactPortraitProps {
  lng: Language;
  contact: WorkbenchContact;
  /** A contact met in mail: nothing to read or change. */
  readOnly: boolean;
  /** The published ceiling of a picture. */
  maxBytes: number;
}

/** The blob of a contact's photo, read again whenever `version` moves. */
function usePhoto(id: string, version: number, enabled: boolean): string | null {
  const [shown, setShown] = useState<{ id: string; url: string | null } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const stop = new AbortController();
    let url: string | null = null;
    apiClient
      .getResponse(PHOTO_PATH, { params: { id }, signal: stop.signal })
      .then(response => response.blob())
      .then(
        blob => {
          if (stop.signal.aborted) return;
          url = URL.createObjectURL(blob);
          setShown({ id, url });
        },
        () => {
          if (!stop.signal.aborted) setShown({ id, url: null });
        }
      );
    return () => {
      stop.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [id, version, enabled]);

  return shown?.id === id ? shown.url : null;
}

export function ContactPortrait({ lng, contact, readOnly, maxBytes }: ContactPortraitProps) {
  const { t } = useTranslation(lng);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const url = usePhoto(contact.id, version, !readOnly);
  const { mutate: put } = useApiMutation<FormData, void>({
    method: 'PUT',
    componentName: 'WorkbenchContacts',
  });
  const { mutate: del } = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: 'WorkbenchContacts',
  });
  const name = contactName(contact) || t('workbench.contacts.no_name');

  const act = async (run: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await run();
      setVersion(current => current + 1);
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed'));
    } finally {
      setBusy(false);
    }
  };

  const picked = (event: ChangeEvent<HTMLInputElement>) => {
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
    form.append('id', contact.id);
    form.append('file', file);
    void act(() => put(PHOTO_PATH, form));
  };

  return (
    <div className="flex items-center gap-3">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- a blob of the API's own answer
        <img src={url} alt={name} className="h-16 w-16 shrink-0 rounded-full object-cover" />
      ) : (
        <span
          aria-hidden="true"
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-muted text-lg font-semibold text-foreground"
        >
          {contactInitials(contact)}
        </span>
      )}
      {!readOnly && (
        <div className="flex gap-1">
          <input
            ref={input}
            type="file"
            accept="image/*"
            aria-label={t('workbench.contacts.photo_file')}
            className="sr-only"
            tabIndex={-1}
            onChange={picked}
          />
          <Button
            variant="ghost"
            size="icon"
            isLoading={busy}
            aria-label={t('workbench.contacts.photo_change')}
            title={t('workbench.contacts.photo_change')}
            onClick={() => input.current?.click()}
          >
            <Camera className="h-4 w-4" aria-hidden="true" />
          </Button>
          {url && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={t('workbench.contacts.photo_remove')}
              title={t('workbench.contacts.photo_remove')}
              onClick={() =>
                void act(() => del(PHOTO_PATH, undefined, { params: { id: contact.id } }))
              }
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
