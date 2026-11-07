'use client';

/**
 * ContactImport — a vCard file becomes contacts (ADR-369, lot 9).
 *
 * The person picks a file; it leaves under one key (a replay makes nothing twice) and the API
 * answers card by card. Every card that made it is counted, and every one that did not is named
 * in a report that stays until it is read. A file past the published ceiling is refused unsent.
 */
import { Upload } from 'lucide-react';
import { useRef, useState, type ChangeEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { WORKBENCH_HEADER_ICON } from '@/lib/workbench/tools';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { ContactsImported } from '@/lib/workbench/types';
import { generateUUID } from '@/lib/utils';
import { ToolActions, ToolDialogHeader } from '../ToolForm';

const BYTES_PER_MEGABYTE = 1024 * 1024;

export interface ContactImportProps {
  lng: Language;
  /** The published ceiling of a file. */
  maxBytes: number;
  /** Contacts arrived: the list reads them. */
  onImported: () => Promise<unknown>;
}

export function ContactImport({ lng, maxBytes, onImported }: ContactImportProps) {
  const { t } = useTranslation(lng);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ContactsImported | null>(null);
  const { mutate: post } = useApiMutation<FormData, ContactsImported>({
    method: 'POST',
    componentName: 'WorkbenchContacts',
  });

  const send = async (file: File) => {
    if (file.size > maxBytes) {
      toast.error(
        t('workbench.errors.too_large_bounded', {
          megabytes: Number((maxBytes / BYTES_PER_MEGABYTE).toFixed(1)),
        })
      );
      return;
    }
    const form = new FormData();
    form.append('idempotency_key', generateUUID());
    form.append('file', file);
    setBusy(true);
    try {
      const answer = await post('/workbench/contacts/import', form);
      await onImported();
      if (answer?.failed.length) setReport(answer);
      else toast.success(t('workbench.contacts.imported', { count: answer?.done ?? 0 }));
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.contacts.failed'));
    } finally {
      setBusy(false);
    }
  };

  const picked = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Emptied at once: the same file picked again is a new choice, not no change.
    event.target.value = '';
    if (file) void send(file);
  };

  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".vcf,text/vcard"
        aria-label={t('workbench.contacts.import_file')}
        className="sr-only"
        tabIndex={-1}
        onChange={picked}
      />
      <Button
        variant="outline"
        size="icon"
        className={WORKBENCH_HEADER_ICON}
        isLoading={busy}
        aria-label={t('workbench.contacts.import')}
        title={t('workbench.contacts.import')}
        onClick={() => input.current?.click()}
      >
        <Upload className="h-4 w-4" aria-hidden="true" />
      </Button>
      {report && (
        <Dialog open onOpenChange={open => !open && setReport(null)}>
          <DialogContent className="sm:max-w-md">
            <ToolDialogHeader>
              <DialogTitle>{t('workbench.contacts.import_report_title')}</DialogTitle>
              <DialogDescription>
                {t('workbench.contacts.imported', { count: report.done })}
              </DialogDescription>
            </ToolDialogHeader>
            <ul className="max-h-64 space-y-1 overflow-y-auto text-sm">
              {report.failed.map(card => (
                <li key={card.position} className="break-words">
                  {card.name
                    ? t('workbench.contacts.import_card', {
                        position: card.position,
                        name: card.name,
                      })
                    : t('workbench.contacts.import_card_unnamed', { position: card.position })}
                </li>
              ))}
            </ul>
            <ToolActions>
              <Button onClick={() => setReport(null)}>{t('common.close')}</Button>
            </ToolActions>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
