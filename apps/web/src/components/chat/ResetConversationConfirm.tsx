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
 * The wording was also wrong. It announced "the conversation history", while
 * `POST /conversations/me/reset` additionally purges **every attachment of the
 * user** — AI-generated images included — the token summaries, the LangGraph
 * checkpoints and the tool contexts. The dialog now says what actually
 * happens: a user who is about to lose their generated images deserves to know
 * before, not after.
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
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={onConfirm}
          >
            {t('chat.reset_confirm.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
