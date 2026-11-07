'use client';

/**
 * FileTextEditor — a text file changed by the person's own hand (ADR-369, lot 14).
 *
 * The words are read when the window opens, with the version they are at, and written back on
 * that version: an edit made elsewhere meanwhile is refused, the words typed stay on the screen,
 * and the current version is one click away. Leaving with words unsaved asks first. Nothing here
 * reaches a model unless the person asks LIA to write (`FieldAssist`, ADR-372): its words join the
 * field, and the click on « Save » stays the confirmation.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchFileDetail, WorkbenchFileText } from '@/lib/workbench/types';

import { FieldAssist } from '../assist/FieldAssist';
import { CancelButton, ToolActions, ToolDialogHeader, useToolConfirm } from '../ToolForm';

const TEXT_PATH = '/workbench/files/text';
const CONFLICT_KEY = 'workbench.errors.conflict';

export interface FileTextEditorProps {
  lng: Language;
  file: WorkbenchFileDetail;
  onClose: () => void;
  /** The words were written. */
  onSaved: () => void;
}

export function FileTextEditor({ lng, file, onClose, onSaved }: FileTextEditorProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useToolConfirm();
  const { id } = file;
  const {
    data: held,
    error,
    refetchVerified,
  } = useApiQuery<WorkbenchFileText>(TEXT_PATH, {
    componentName: 'FileTextEditor',
    params: { id },
    deps: [id],
  });
  /** What the person typed over the words read. */
  const [typed, setTyped] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const text = typed ?? held?.text ?? '';
  const failed = error !== null;

  const reload = async () => {
    if (!(await refetchVerified())) return;
    setTyped(null);
    setRefusal(null);
  };
  const dirty = held !== undefined && text !== held.text;
  const leave = async () => {
    if (dirty) {
      const left = await confirm({
        title: t('workbench.files.text_leave_title'),
        description: t('workbench.files.text_leave_body'),
        confirmLabel: t('workbench.files.text_leave'),
      });
      if (!left) return;
    }
    onClose();
  };
  const save = async () => {
    if (held === undefined) return;
    setSaving(true);
    setRefusal(null);
    try {
      await apiClient.put(TEXT_PATH, { id, text, tag: held.tag });
      toast.success(t('workbench.files.text_saved'));
      onSaved();
      onClose();
    } catch (error: unknown) {
      const named = workbenchRefusal(error);
      setRefusal(named?.key ?? 'workbench.files.text_save_failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open onOpenChange={open => !open && void leave()}>
        <DialogContent className="sm:max-w-3xl">
          <ToolDialogHeader>
            <DialogTitle className="truncate">
              {t('workbench.files.edit_title', { name: file.name })}
            </DialogTitle>
            <DialogDescription className="sr-only">
              {t('workbench.files.text_field')}
            </DialogDescription>
          </ToolDialogHeader>
          {failed && <p className="text-sm">{t('workbench.files.text_read_failed')}</p>}
          {!failed && held === undefined && <Skeleton className="h-64 w-full" />}
          {held !== undefined && (
            <Textarea
              label={t('workbench.files.text_field')}
              labelEnd={<FieldAssist lng={lng} kind="document" value={text} onChange={setTyped} />}
              value={text}
              onChange={event => setTyped(event.target.value)}
              spellCheck={false}
              className="min-h-[50dvh] font-mono text-sm"
            />
          )}
          {refusal && (
            <Alert variant="error">
              <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                <span>{t(refusal)}</span>
                {refusal === CONFLICT_KEY && (
                  <Button variant="outline" size="sm" onClick={() => void reload()}>
                    {t('workbench.files.text_reload')}
                  </Button>
                )}
              </AlertDescription>
            </Alert>
          )}
          <ToolActions>
            <CancelButton lng={lng} onClick={() => void leave()} />
            <Button disabled={!dirty || saving} onClick={() => void save()}>
              {t('workbench.files.text_save')}
            </Button>
          </ToolActions>
        </DialogContent>
      </Dialog>
      {confirmDialog}
    </>
  );
}
