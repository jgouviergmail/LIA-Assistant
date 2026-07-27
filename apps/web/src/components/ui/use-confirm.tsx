'use client';

/**
 * A promise-based replacement for `window.confirm` (W4b).
 *
 * ## Why
 *
 * Nine destructive admin actions — deleting a user, ERASING a user, rewriting
 * pricing tables — still went through the native `confirm()`. That dialog
 * ignores the theme and the typography, takes its OK/Cancel labels from the
 * operating system rather than the app's language (so a French UI shows English
 * buttons on Windows), blocks the main thread, and is silently suppressed by
 * some browsers when several fire in a row. On the most irreversible actions of
 * the product, the least cared-for surface was exactly the wrong trade.
 *
 * ## Why a hook rather than nine components
 *
 * The call sites all read `const confirmed = confirm(msg); if (!confirmed)
 * return;`. Keeping that shape — `const confirmed = await confirm({...})` —
 * makes each migration a two-line change instead of a component extraction, and
 * avoids nine near-identical dialogs drifting apart. The dialog element itself
 * is returned and rendered by the caller, so it stays inside the caller's tree
 * (no portal-owning singleton, no global state).
 *
 * The promise resolves `false` on cancel, on Escape, and on outside-click —
 * dismissal is never taken for consent.
 */

import { useCallback, useRef, useState } from 'react';
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

export interface ConfirmOptions {
  /** Short question — what is about to happen. */
  title: string;
  /** The consequence, stated plainly. Rendered as text, never as HTML. */
  description?: string;
  /** Label of the confirming button (defaults to the shared "Confirm"). */
  confirmLabel?: string;
  /** Styles the confirming button as destructive. Defaults to true: every
   *  current caller is an irreversible admin action. */
  destructive?: boolean;
}

export interface UseConfirmReturn {
  /** Ask the user. Resolves true only on an explicit confirmation. */
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  /** Render this in the caller's tree for the dialog to exist. */
  confirmDialog: React.ReactNode;
}

export function useConfirm(): UseConfirmReturn {
  const { t } = useTranslation();
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  // The pending promise's resolver. A ref, not state: resolving must not wait
  // for a re-render, and two rapid asks must not resolve the same deferred.
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const settle = useCallback((value: boolean) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setOptions(null);
    resolve?.(value);
  }, []);

  const confirm = useCallback(
    (next: ConfirmOptions) =>
      new Promise<boolean>(resolve => {
        // A previous question still open is answered "no" rather than left
        // hanging forever — an unresolved promise would freeze its caller.
        resolverRef.current?.(false);
        resolverRef.current = resolve;
        setOptions(next);
      }),
    []
  );

  const confirmDialog = (
    <AlertDialog
      open={options !== null}
      onOpenChange={open => {
        // Escape and outside-click land here: dismissal is a refusal.
        if (!open) settle(false);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{options?.title ?? ''}</AlertDialogTitle>
          {options?.description && (
            <AlertDialogDescription className="whitespace-pre-line">
              {options.description}
            </AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => settle(false)}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            className={
              options?.destructive === false
                ? undefined
                : 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
            }
            onClick={() => settle(true)}
          >
            {options?.confirmLabel ?? t('common.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirm, confirmDialog };
}
