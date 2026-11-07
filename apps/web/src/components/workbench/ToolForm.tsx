'use client';

/**
 * ToolForm — how every form of the Tools opens and ends (owner, 2026-11-06).
 *
 * A head that starts at the left at every width. Acts that end the form: on a phone each on its own
 * line and the whole width, the act first; from `sm` side by side at the end of the line. A
 * « Cancel » that wears « Delete »'s style on every screen, confirmations included, so the way out
 * looks the same wherever it is met. A tool draws none of these itself
 * (`toolForm.guard.test.ts`), which is what keeps one tool's form from drifting from another's.
 */
import { forwardRef, type HTMLAttributes } from 'react';

import { Button, type ButtonProps } from '@/components/ui/button';
import { DialogHeader } from '@/components/ui/dialog';
import { useConfirm, type ConfirmLook, type UseConfirmReturn } from '@/components/ui/use-confirm';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';

const TOOL_CONFIRM: ConfirmLook = { cancelVariant: 'destructive', headerClassName: 'text-left' };

/** A dialog's title and what it says, from the left at every width. */
export function ToolDialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <DialogHeader className={cn('text-left', className)} {...props} />;
}

/** What ends a form, in reading order: « Cancel » first, the act last. */
export function ToolActions({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end',
        className
      )}
      {...props}
    />
  );
}

export interface CancelButtonProps extends Omit<ButtonProps, 'variant' | 'children'> {
  lng: Language;
  /** Its word, where taking something back is said otherwise. */
  label?: string;
}

/** The way out of a form. */
export const CancelButton = forwardRef<HTMLButtonElement, CancelButtonProps>(function CancelButton(
  { lng, label, type = 'button', ...props },
  ref
) {
  const { t } = useTranslation(lng);
  return (
    <Button ref={ref} type={type} variant="destructive" {...props}>
      {label ?? t('common.cancel')}
    </Button>
  );
});

/** A question before an act, its « Cancel » and its head as every form's. */
export function useToolConfirm(): UseConfirmReturn {
  return useConfirm(TOOL_CONFIRM);
}
