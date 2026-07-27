'use client';

/**
 * Confirmation for disconnecting a connector (W4a).
 *
 * Replaces a native `window.confirm`: an OS dialog ignores the theme, the
 * chosen typography and the app's language — its buttons are labelled by the
 * operating system, so a French user could be asked "OK / Cancel" in English —
 * and it blocks the main thread.
 *
 * The connector is named in the body: "disconnect this service" gave no way to
 * tell which card had been clicked, which matters on a page listing several.
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

export interface DisconnectConnectorConfirmProps {
  /** Open when a connector is pending confirmation. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Human label of the connector being disconnected, e.g. "Gmail". */
  connectorLabel: string;
  /** Runs only on confirmation; the caller owns the request and its errors. */
  onConfirm: () => void;
}

export function DisconnectConnectorConfirm({
  open,
  onOpenChange,
  connectorLabel,
  onConfirm,
}: DisconnectConnectorConfirmProps) {
  const { t } = useTranslation();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t('settings.connectors.disconnect_title', { name: connectorLabel })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('settings.connectors.disconnect_description', { name: connectorLabel })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={onConfirm}
          >
            {t('settings.connectors.disconnect')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
