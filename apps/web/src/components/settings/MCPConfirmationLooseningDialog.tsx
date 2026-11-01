'use client';

import type { TFunction } from 'i18next';
import { ShieldAlert } from 'lucide-react';

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
import type { MCPQuestionLoss } from '@/lib/mcp-behavior';

/** At most this many rows are listed; the rest is counted, never dropped in silence. */
export const LOOSENING_ROWS_SHOWN = 12;

interface Props {
  /** The questions the change would remove; the dialog is open while there are some. */
  losses: readonly MCPQuestionLoss[] | null;
  onConfirm: () => void;
  onCancel: () => void;
  t: TFunction;
}

/**
 * The alert before a change that makes LIA ask less (owner decision 2026-10-30).
 *
 * Nothing is locked: the person stays responsible for the setting and confirms it
 * knowing what LIA will no longer ask about. The list comes from the API's own
 * computation (`questions_lost`, one row per tool: a tool asked about is asked in
 * both modes); a tool's name is a third party's text and is rendered as text.
 */
export function MCPConfirmationLooseningDialog({ losses, onConfirm, onCancel, t }: Props) {
  const rows = losses ?? [];
  const shown = rows.slice(0, LOOSENING_ROWS_SHOWN);
  const hidden = rows.length - shown.length;
  return (
    <AlertDialog
      open={losses !== null && losses.length > 0}
      onOpenChange={open => !open && onCancel()}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            {t('settings.mcp.loosening.title')}
          </AlertDialogTitle>
          <AlertDialogDescription>{t('settings.mcp.loosening.body')}</AlertDialogDescription>
        </AlertDialogHeader>
        <ul className="max-h-60 space-y-1 overflow-y-auto text-sm">
          {shown.map(loss => (
            <li key={`${loss.server_id}:${loss.tool_name}`} className="break-words">
              <span className="font-medium">{loss.tool_name}</span>
              <span className="text-muted-foreground">
                {' — '}
                {loss.server_name}
              </span>
            </li>
          ))}
        </ul>
        {hidden > 0 && (
          <p className="text-xs text-muted-foreground">
            {t('settings.mcp.loosening.more', { count: hidden })}
          </p>
        )}
        <p className="text-sm text-foreground">{t('settings.mcp.loosening.responsibility')}</p>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            {t('settings.mcp.loosening.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
