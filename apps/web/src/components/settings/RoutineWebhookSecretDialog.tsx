'use client';

import { KeyRound } from '@/lib/icons';
import { useTranslation } from 'react-i18next';

import { CopyValueField } from '@/components/settings/CopyValueField';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { RoutineWebhookSecret } from '@/hooks/useScheduledActions';
import { signedCallExample } from '@/lib/routine-webhook';

interface RoutineWebhookSecretDialogProps {
  /** The address and the secret just drawn; null keeps the dialog closed. */
  drawn: RoutineWebhookSecret | null;
  onClose: () => void;
}

/**
 * A routine's address and the secret just drawn, shown THIS once (ADR-386).
 *
 * The secret leaves the server in the answer of the request that drew it and
 * nowhere else, so this dialog is the only moment the person can copy it: it
 * says so, and closes on an explicit « copied » rather than on a stray click.
 *
 * Read whole on a phone: the dialog's one column may shrink below its content
 * (a grid track is otherwise as wide as its longest unbreakable line, and the
 * signed-call example pushed the dialog past the screen); the values and the
 * example wrap instead. Nothing here is offered to the selection assist: it
 * would hand a selected secret to a model.
 */
export function RoutineWebhookSecretDialog({ drawn, onClose }: RoutineWebhookSecretDialogProps) {
  const { t } = useTranslation();
  const copied = t('scheduled_actions.webhook.copied');
  return (
    <Dialog open={drawn !== null} onOpenChange={open => !open && onClose()}>
      <DialogContent
        className="grid-cols-[minmax(0,1fr)] sm:max-w-2xl"
        onInteractOutside={event => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            {t('scheduled_actions.webhook.secret_title')}
          </DialogTitle>
          <DialogDescription>{t('scheduled_actions.webhook.secret_description')}</DialogDescription>
        </DialogHeader>
        {drawn && (
          <div className="min-w-0 space-y-5" data-selection-assist="off">
            <Alert variant="warning">
              <Alert.Icon variant="warning" />
              <Alert.Content>{t('scheduled_actions.webhook.shown_once')}</Alert.Content>
            </Alert>
            <CopyValueField
              id="routine-webhook-url"
              label={t('scheduled_actions.webhook.address')}
              value={drawn.webhook_url}
              copyLabel={t('scheduled_actions.webhook.copy_address')}
              copiedMessage={copied}
            />
            <CopyValueField
              id="routine-webhook-secret"
              label={t('scheduled_actions.webhook.secret')}
              value={drawn.webhook_secret}
              copyLabel={t('scheduled_actions.webhook.copy_secret')}
              copiedMessage={copied}
            />
            <figure className="min-w-0 space-y-3" aria-labelledby="routine-webhook-example">
              <figcaption id="routine-webhook-example" className="text-sm font-medium leading-none">
                {t('scheduled_actions.webhook.example')}
              </figcaption>
              <p className="text-xs text-muted-foreground">
                {t('scheduled_actions.webhook.example_hint')}
              </p>
              <pre className="select-all whitespace-pre-wrap wrap-anywhere rounded-md border bg-muted p-3 font-mono text-xs leading-relaxed">
                <code>{signedCallExample(drawn)}</code>
              </pre>
            </figure>
          </div>
        )}
        <DialogFooter>
          <Button onClick={onClose}>{t('scheduled_actions.webhook.done')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
