'use client';

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApplicationFileUploadControls } from './ApplicationFileUploadControls';
import { useApplicationSkillFileUpload } from '@/hooks/useApplicationSkillFileUpload';
import { useApplicationCommandDeadline } from '@/hooks/useApplicationCommandDeadline';
import { skillFileUploadReceiptSchema } from '@/lib/application-skill-file-upload';
import { formatFileSize } from '@/lib/format';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const copy = 'settings.application_tools';
type UploadAction = ReturnType<typeof useApplicationSkillFileUpload>;

function uploadMessage(
  status: ApplicationCommandStatus,
  action: UploadAction,
  expired: boolean
): string {
  const receipt = skillFileUploadReceiptSchema.safeParse(status.outcome?.values);
  if (action.mode === 'accepted' || (status.outcome?.committed === true && receipt.success))
    return 'skill_file_upload_accepted';
  if (action.mode === 'uncertain' || status.outcome?.error_code === 'COMPLETION_UNKNOWN')
    return 'secure_unknown';
  if (expired) return 'secure_expired';
  if (action.mode === 'sending') return 'skill_file_upload_sending';
  if (action.waiting && action.selection) return 'skill_file_upload_waiting';
  return 'secure_failed';
}

export function ApplicationSkillFileUploadCard({
  status,
  checkResult,
  readError,
}: {
  status: ApplicationCommandStatus;
  checkResult: () => Promise<void>;
  readError: Error | null;
}) {
  const { t } = useTranslation();
  const action = useApplicationSkillFileUpload(status, checkResult);
  const checkButton = useRef<HTMLButtonElement>(null);
  const expired = useApplicationCommandDeadline(status.expires_at, action.scopeKey);
  const selection = action.selection;
  const receipt = skillFileUploadReceiptSchema.safeParse(status.outcome?.values);
  const cachePending =
    action.cacheRefreshPending ||
    (status.outcome?.committed === true && receipt.success && receipt.data.cache_refresh_pending);
  return (
    <section
      className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t(`${copy}.skill_file_upload_title`)}
      aria-busy={action.mode === 'sending'}
    >
      <h3 className="flex items-start gap-2 text-sm font-medium">
        <Upload className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${copy}.skill_file_upload_title`)}
      </h3>
      <p className="mt-1 break-words text-sm text-muted-foreground" role="status">
        {t(`${copy}.${uploadMessage(status, action, expired)}`)}
      </p>
      {selection && (
        <div className="mt-2 min-w-0 space-y-1 text-sm">
          <p className="break-all">
            {selection.previous
              ? t(`${copy}.skill_file_upload_replace`, { name: selection.previous.name })
              : t(`${copy}.skill_file_upload_new`)}
          </p>
          <p>
            {t(`${copy}.skill_file_upload_limits`, {
              size: formatFileSize(selection.max_file_size_bytes),
              files: selection.max_package_files,
              unpacked: formatFileSize(selection.max_decompressed_bytes),
            })}
          </p>
          <p>{t(`${copy}.skill_file_upload_effects`)}</p>
        </div>
      )}
      {action.waiting && !expired && selection && (
        <ApplicationFileUploadControls
          action={action}
          maxBytes={selection.max_file_size_bytes}
          accept={selection.allowed_extensions.join(',')}
          copyPrefix="skill_file_upload"
          onAccepted={() => checkButton.current?.focus()}
        />
      )}
      {action.mode === 'sending' && (
        <p className="mt-2 text-sm" role="status">
          {t(`${copy}.document_upload_progress`, { progress: action.progress })}
        </p>
      )}
      {cachePending && (
        <p className="mt-2 text-sm" role="status">
          {t(`${copy}.skill_file_upload_cache_pending`)}
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
