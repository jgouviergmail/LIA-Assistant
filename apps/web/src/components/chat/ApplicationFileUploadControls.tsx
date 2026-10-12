'use client';

import { useId, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { formatFileSize } from '@/lib/format';
import type { UploadMode } from '@/hooks/useApplicationFileUpload';

interface FileUploadAction {
  scopeKey: string | undefined;
  file: File | null;
  mode: UploadMode;
  choose: (file: File | null) => void;
  confirm: (onAccepted?: () => void) => void;
}

export function ApplicationFileUploadControls({
  action,
  maxBytes,
  accept,
  copyPrefix,
  onAccepted,
}: {
  action: FileUploadAction;
  maxBytes: number;
  accept: string;
  copyPrefix: 'document_upload' | 'skill_file_upload' | 'plugin_file_upload';
  onAccepted: () => void;
}) {
  const { t } = useTranslation();
  const inputId = useId();
  const confirmButton = useRef<HTMLButtonElement>(null);
  const oversize = !!action.file && action.file.size > maxBytes;
  const canConfirm = action.mode === 'idle' && !!action.file && !oversize;
  const copy = `settings.application_tools.${copyPrefix}`;
  return (
    <div className="mt-3 min-w-0 space-y-2">
      <label htmlFor={inputId} className="block text-sm font-medium">
        {t(`${copy}_choose`)}
      </label>
      <input
        key={`${action.scopeKey}:${action.mode === 'accepted'}`}
        id={inputId}
        type="file"
        className="w-full min-w-0 text-sm"
        aria-label={t(`${copy}_choose`)}
        accept={accept}
        aria-disabled={action.mode !== 'idle'}
        onClick={event => {
          if (action.mode !== 'idle') event.preventDefault();
        }}
        onChange={event => action.choose(event.currentTarget.files?.[0] ?? null)}
      />
      {action.file && (
        <p className="break-all text-sm">
          {action.file.name} — {formatFileSize(action.file.size)}
        </p>
      )}
      {oversize && (
        <p role="alert" className="text-sm text-destructive">
          {t(`${copy}_too_large`)}
        </p>
      )}
      <Button
        ref={confirmButton}
        type="button"
        size="sm"
        aria-disabled={!canConfirm}
        onClick={() => {
          if (canConfirm)
            action.confirm(() => {
              if (document.activeElement === confirmButton.current) onAccepted();
            });
        }}
      >
        {t(`${copy}_confirm`)}
      </Button>
    </div>
  );
}
