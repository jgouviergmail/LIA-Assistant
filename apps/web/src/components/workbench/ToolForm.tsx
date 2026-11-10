'use client';

/**
 * ToolForm — how every form of the Tools opens and ends (owner, 2026-11-06).
 *
 * A head that starts at the left at every width. Acts that end the form: on a phone each on its own
 * line and the whole width, the act first; from `sm` side by side at the end of the line. A
 * neutral « Cancel » on every screen, confirmations included, so the way out
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

const TOOL_CONFIRM: ConfirmLook = { cancelVariant: 'outline', headerClassName: 'text-left' };

/**
 * A long form of the Tools: the whole screen on a phone, where a framed window would leave its
 * fields a strip; above `sm` the window the caller sizes (`sm:max-w-*`).
 */
export const TOOL_FORM_SCREEN =
  'max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0';

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
    <Button ref={ref} type={type} variant="outline" {...props}>
      {label ?? t('common.cancel')}
    </Button>
  );
});

/** A question before an act, its « Cancel » and its head as every form's. */
export function useToolConfirm(): UseConfirmReturn {
  return useConfirm(TOOL_CONFIRM);
}
