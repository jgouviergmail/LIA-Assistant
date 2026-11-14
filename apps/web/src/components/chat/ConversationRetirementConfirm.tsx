'use client';

import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { getApiErrorStatus } from '@/lib/api-error';
import { generateUUID } from '@/lib/utils';
import type { ConversationOperation, ConversationSummary } from '@/types/conversation';

interface RetirementConfirmProps {
  action: ConversationOperation;
  target: ConversationSummary;
  onConfirm: (target: ConversationSummary, operationId: string) => Promise<void>;
  onClose: () => void;
}

function readField(value: unknown, key: string): unknown {
  return value !== null && typeof value === 'object' && key in value
    ? Reflect.get(value, key)
    : undefined;
}

function refusalKey(error: unknown): string {
  const detail = readField(readField(error, 'data'), 'detail');
  switch (readField(detail, 'error')) {
    case 'conversation_busy':
      return 'chat.discussions.operation_busy';
    case 'conversation_changed':
      return 'chat.discussions.operation_changed';
  }
  return getApiErrorStatus(error) === 404
    ? 'chat.discussions.unavailable'
    : 'chat.discussions.operation_error';
}

/** One dialog instance owns the reviewed generation and its retry identity. */
export function ConversationRetirementConfirm({
  action,
  target,
  onConfirm,
  onClose,
}: RetirementConfirmProps) {
  const { t } = useTranslation();
  const [reviewed] = useState(() => ({ ...target }));
  const [operationId] = useState(generateUUID);
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string>();
  const inFlight = useRef(false);
  const title = reviewed.kind === 'main' ? t('chat.discussions.main') : reviewed.title;

  async function confirm() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrorKey(undefined);
    try {
      await onConfirm(reviewed, operationId);
      onClose();
    } catch (error) {
      setErrorKey(refusalKey(error));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <AlertDialog
      open
      onOpenChange={open => {
        if (!open && !inFlight.current) onClose();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="wrap-anywhere">
            {t(`chat.discussions.${action}_title`, { title })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t(`chat.discussions.${action}_description`)}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {errorKey && (
          <p role="alert" className="text-sm text-destructive">
            {t(errorKey)}
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
          <Button
            type="button"
            variant="destructive"
            isLoading={busy}
            onClick={() => void confirm()}
          >
            {t(`chat.discussions.${action}`)}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
