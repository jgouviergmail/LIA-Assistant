'use client';

/**
 * Confirmation for resetting the conversation (W4a).
 *
 * Replaces a native `window.confirm`: an OS dialog ignores the theme, the
 * chosen typography and the app's language (its OK/Cancel come from the
 * operating system), and it blocks the main thread. On the most destructive
 * action of the product, the least cared-for surface was exactly the wrong
 * trade.
 *
 * The wording must say what `POST /conversations/me/reset` actually removes:
 * the messages, the files the person attached, the token summaries, the
 * LangGraph checkpoints and the tool contexts. Since ADR-279 the files LIA
 * generated SURVIVE a reset (they belong to « My generated files »), and the
 * dialog kept promising their deletion until 2026-09-25 — a false alarm is a
 * wrong statement too. The other open tabs empty themselves once it commits
 * (ADR-320).
 */

import { useTranslation } from 'react-i18next';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export interface ResetConversationConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Runs only on confirmation; the caller owns the request and its errors. */
  onConfirm: () => void;
}

export function ResetConversationConfirm({
  open,
  onOpenChange,
  onConfirm,
}: ResetConversationConfirmProps) {
  const { t } = useTranslation();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('chat.reset_confirm.title')}</AlertDialogTitle>
          <AlertDialogDescription>{t('chat.reset_confirm.description')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('chat.reset_confirm.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
