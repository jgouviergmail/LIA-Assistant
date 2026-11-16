'use client';

/**
 * The ntfy block of the notification settings (ADR-391).
 *
 * ntfy brings LIA's notifications to a phone or a computer with or without Google services: the
 * person subscribes the free ntfy app to a TOPIC that LIA publishes to. This block lists the
 * account's subscriptions, adds one (on the instance's server or on another), and shows how to
 * subscribe a device. It renders nothing while the capability is not offered — the operator's
 * switch closes the routes (ADR-280), so nothing is read either.
 */

import * as React from 'react';

import { BellRing, Plus } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useAppConfig } from '@/hooks/useAppConfig';
import {
  useNtfySubscriptions,
  type NtfyOverview,
  type NtfySubscriptionView,
} from '@/hooks/useNtfySubscriptions';
import { capabilityAvailable } from '@/lib/capability-availability';
import { NtfyDeviceDialog } from './NtfyDeviceDialog';
import { NtfySubscriptionDialog } from './NtfySubscriptionDialog';
import { NtfySubscriptionRow } from './NtfySubscriptionRow';

interface NtfySettingsProps {
  lng: Language;
}

export function NtfySettings({ lng }: NtfySettingsProps) {
  const { config } = useAppConfig();
  const offered = capabilityAvailable(config, 'ntfy');
  const ntfy = useNtfySubscriptions(offered);
  if (!offered) return null;
  return <NtfyBlock lng={lng} ntfy={ntfy} />;
}

type NtfyState = ReturnType<typeof useNtfySubscriptions>;

function NtfyBlock({ lng, ntfy }: NtfySettingsProps & { ntfy: NtfyState }) {
  const { t } = useTranslation(lng);
  const [adding, setAdding] = React.useState(false);
  const [device, setDevice] = React.useState<NtfySubscriptionView | null>(null);
  const { overview } = ntfy;

  return (
    <section className="space-y-3" aria-busy={ntfy.refreshing || undefined}>
      <div className="space-y-1">
        <h4 className="flex items-center gap-2 text-sm font-medium">
          <BellRing className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('settings.notifications.ntfy.title')}
        </h4>
        <p className="text-xs text-muted-foreground">
          {t('settings.notifications.ntfy.description')}
        </p>
      </div>

      <NtfyBody lng={lng} ntfy={ntfy} onAdd={() => setAdding(true)} onSubscribeDevice={setDevice} />

      {overview && (
        <NtfySubscriptionDialog
          lng={lng}
          open={adding}
          onOpenChange={setAdding}
          overview={overview}
          onCreate={ntfy.create}
          onCreated={created => {
            setAdding(false);
            setDevice(created);
          }}
        />
      )}

      <NtfyDeviceDialog
        lng={lng}
        subscription={device}
        onOpenChange={open => {
          if (!open) setDevice(null);
        }}
      />
    </section>
  );
}

/** What the account holds: the first load, a read that failed, or the list and its add. */
function NtfyBody({
  lng,
  ntfy,
  onAdd,
  onSubscribeDevice,
}: NtfySettingsProps & {
  ntfy: NtfyState;
  onAdd: () => void;
  onSubscribeDevice: (subscription: NtfySubscriptionView) => void;
}) {
  const { t } = useTranslation(lng);
  const { overview } = ntfy;
  if (ntfy.firstLoad) {
    return (
      <Skeleton
        className="h-16 w-full rounded-lg"
        label={t('settings.notifications.ntfy.loading')}
      />
    );
  }
  if (!overview) {
    return ntfy.readFailed ? (
      <InfoBox variant="error" className="p-3">
        <p className="text-sm">{t('settings.notifications.ntfy.read_error')}</p>
      </InfoBox>
    ) : null;
  }
  const { subscriptions } = overview;
  const canSubscribe = !!overview.instance_url || overview.custom_servers_enabled;
  return (
    <>
      {subscriptions.length > 0 && (
        <ul className="space-y-2">
          {subscriptions.map(subscription => (
            <NtfySubscriptionRow
              key={subscription.id}
              lng={lng}
              subscription={subscription}
              onUpdate={ntfy.update}
              onTest={ntfy.test}
              onRemove={ntfy.remove}
              onSubscribeDevice={onSubscribeDevice}
            />
          ))}
        </ul>
      )}
      {canSubscribe ? (
        <NtfyAdd lng={lng} overview={overview} onAdd={onAdd} />
      ) : (
        subscriptions.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {t('settings.notifications.ntfy.nothing_offered')}
          </p>
        )
      )}
    </>
  );
}

/** The add control: offered within the ceiling, its limit said instead of a refusal. */
function NtfyAdd({
  lng,
  overview,
  onAdd,
}: NtfySettingsProps & { overview: NtfyOverview; onAdd: () => void }) {
  const { t } = useTranslation(lng);
  const limitId = React.useId();
  const atLimit = overview.subscriptions.length >= overview.max_subscriptions;
  return (
    <div className="space-y-2">
      {overview.subscriptions.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('settings.notifications.ntfy.empty')}</p>
      )}
      {atLimit && (
        <p className="text-xs text-muted-foreground" id={limitId}>
          {t('settings.notifications.ntfy.limit_reached', { max: overview.max_subscriptions })}
        </p>
      )}
      <Button
        type="button"
        size="sm"
        // Inert at the ceiling, never removed: focus comes back here when the dialog closes.
        className="aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
        aria-disabled={atLimit || undefined}
        aria-describedby={atLimit ? limitId : undefined}
        onClick={() => {
          if (!atLimit) onAdd();
        }}
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t('settings.notifications.ntfy.add')}
      </Button>
    </div>
  );
}
