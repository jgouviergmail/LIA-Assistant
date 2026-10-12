'use client';

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApplicationFileUploadControls } from './ApplicationFileUploadControls';
import { useApplicationDocumentUpload } from '@/hooks/useApplicationDocumentUpload';
import { useApplicationCommandDeadline } from '@/hooks/useApplicationCommandDeadline';
import { formatFileSize } from '@/lib/format';
import type { DocumentUploadSelection } from '@/lib/application-document-upload';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const copy = 'settings.application_tools';
type UploadAction = ReturnType<typeof useApplicationDocumentUpload>;
interface Props {
  status: ApplicationCommandStatus;
  checkResult: () => Promise<void>;
  readError: Error | null;
}

function uploadMessage(
  status: ApplicationCommandStatus,
  action: UploadAction,
  expired: boolean
): string {
  if (action.mode === 'accepted' || status.outcome?.committed === true)
    return 'document_upload_accepted';
  if (action.mode === 'uncertain' || status.outcome?.error_code === 'COMPLETION_UNKNOWN')
    return 'secure_unknown';
  if (expired) return 'secure_expired';
  if (action.mode === 'sending') return 'document_upload_sending';
  if (action.waiting && action.selection) return 'document_upload_waiting';
  return 'secure_failed';
}

function UploadDestination({ selection }: { selection: DocumentUploadSelection }) {
  const { t } = useTranslation();
  return (
    <div className="mt-2 min-w-0 space-y-1 text-sm">
      <p className="break-all">
        {t(`${copy}.document_upload_destination`, { name: selection.space.name })}
      </p>
      <p>
        {t(`${copy}.document_upload_limits`, {
          size: formatFileSize(selection.max_file_size_bytes),
          count: selection.document_count,
          max: selection.max_documents,
        })}
      </p>
      <p className="break-all">
        {t(`${copy}.document_upload_types`, { types: selection.allowed_content_types.join(', ') })}
      </p>
      {!selection.space.is_active && <p>{t(`${copy}.document_upload_inactive`)}</p>}
      <p>{t(`${copy}.document_upload_cost`)}</p>
    </div>
  );
}

export function ApplicationDocumentUploadCard({ status, checkResult, readError }: Props) {
  const { t } = useTranslation();
  const action = useApplicationDocumentUpload(status, checkResult);
  const checkButton = useRef<HTMLButtonElement>(null);
  const expired = useApplicationCommandDeadline(status.expires_at, action.scopeKey);
  const waiting = action.waiting && !expired;
  return (
    <section
      className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t(`${copy}.document_upload_title`)}
      aria-busy={action.mode === 'sending'}
    >
      <h3 className="flex items-start gap-2 text-sm font-medium">
        <Upload className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${copy}.document_upload_title`)}
      </h3>
      <p className="mt-1 break-words text-sm text-muted-foreground" role="status">
        {t(`${copy}.${uploadMessage(status, action, expired)}`)}
      </p>
      {action.selection && <UploadDestination selection={action.selection} />}
      {waiting && action.selection && (
        <ApplicationFileUploadControls
          action={action}
          maxBytes={action.selection.max_file_size_bytes}
          accept={action.selection.allowed_content_types.join(',')}
          copyPrefix="document_upload"
          onAccepted={() => checkButton.current?.focus()}
        />
      )}
      {action.mode === 'sending' && (
        <p className="mt-2 text-sm" role="status">
          {t(`${copy}.document_upload_progress`, { progress: action.progress })}
        </p>
      )}
      {readError && (
        <p role="alert" className="mt-2 text-sm">
          {t(`${copy}.secure_read_failed`)}
        </p>
      )}
      <Button
        ref={checkButton}
        type="button"
        size="sm"
        variant="outline"
        className="mt-2"
        onClick={() => {
          void checkResult();
        }}
      >
        {t(`${copy}.secure_check`)}
      </Button>
    </section>
  );
}
