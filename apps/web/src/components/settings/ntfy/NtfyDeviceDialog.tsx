'use client';

/**
 * How to subscribe a device to an ntfy topic (ADR-391): the QR code a phone scans, the link that
 * opens the ntfy app on the phone itself, and the server and topic to copy into the app on an
 * iPhone or a computer. The QR code is drawn by the API on demand, only while this is open; the
 * topic is a password and the dialog says so.
 */

import { toast } from 'sonner';

import { Copy, ExternalLink } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { InfoBox } from '@/components/ui/info-box';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import type { NtfySubscriptionView } from '@/hooks/useNtfySubscriptions';

interface NtfyDeviceDialogProps {
  lng: Language;
  /** The subscription to subscribe a device to; null: closed. */
  subscription: NtfySubscriptionView | null;
  onOpenChange: (open: boolean) => void;
}

export function NtfyDeviceDialog({ lng, subscription, onOpenChange }: NtfyDeviceDialogProps) {
  const { t } = useTranslation(lng);
  const open = subscription !== null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settings.notifications.ntfy.device.title')}</DialogTitle>
          <DialogDescription>
            {t('settings.notifications.ntfy.device.description')}
          </DialogDescription>
        </DialogHeader>
        {subscription && subscription.topic !== null && (
          <DeviceSteps lng={lng} subscription={subscription} topic={subscription.topic} />
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('settings.notifications.ntfy.device.done')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeviceSteps({
  lng,
  subscription,
  topic,
}: {
  lng: Language;
  subscription: NtfySubscriptionView;
  topic: string;
}) {
  const { t } = useTranslation(lng);
  const qr = useApplicationAccountQuery<{ qr_data_uri: string }>(
    `/notifications/ntfy/${subscription.id}/qr`,
    'NtfyDeviceDialog'
  );

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t('settings.notifications.ntfy.device.copied'));
    } catch {
      toast.error(t('common.copyFailed'));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-center">
        {qr.data ? (
          // eslint-disable-next-line @next/next/no-img-element -- data-URI QR drawn by the API, next/image adds nothing
          <img
            src={qr.data.qr_data_uri}
            alt={t('settings.notifications.ntfy.device.qr_alt')}
            className="h-48 w-48 rounded-lg border bg-white p-2"
          />
        ) : qr.error ? (
          <p className="text-sm text-muted-foreground">
            {t('settings.notifications.ntfy.device.qr_error')}
          </p>
        ) : (
          <Skeleton
            className="h-48 w-48 rounded-lg"
            label={t('settings.notifications.ntfy.device.qr_loading')}
          />
        )}
      </div>

      {subscription.subscribe_link && (
        <Button asChild variant="default" className="w-full">
          <a href={subscription.subscribe_link}>
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t('settings.notifications.ntfy.device.open_app')}
          </a>
        </Button>
      )}

      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>{t('settings.notifications.ntfy.device.android')}</li>
        <li>{t('settings.notifications.ntfy.device.ios')}</li>
      </ul>

      <div className="space-y-4">
        <Input
          label={t('settings.notifications.ntfy.device.server')}
          readOnly
          value={subscription.server_url}
          labelEnd={
            <CopyButton
              label={t('settings.notifications.ntfy.device.copy_server')}
              onCopy={() => void copy(subscription.server_url)}
            />
          }
        />
        <Input
          label={t('settings.notifications.ntfy.device.topic')}
          readOnly
          value={topic}
          spellCheck={false}
          labelEnd={
            <CopyButton
              label={t('settings.notifications.ntfy.device.copy_topic')}
              onCopy={() => void copy(topic)}
            />
          }
        />
      </div>

      <InfoBox variant="warning" className="p-3">
        <p className="text-sm">{t('settings.notifications.ntfy.device.secret')}</p>
      </InfoBox>
    </div>
  );
}

function CopyButton({ label, onCopy }: { label: string; onCopy: () => void }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label={label}
      title={label}
      onClick={onCopy}
    >
      <Copy className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}
