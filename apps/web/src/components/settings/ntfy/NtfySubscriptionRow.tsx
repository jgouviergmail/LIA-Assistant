'use client';

/**
 * One ntfy subscription in the settings (ADR-391): which server, what it receives, whether LIA
 * publishes to it, how the last publication went — and its acts: test, subscribe a device,
 * remove. A subscription whose topic no longer decrypts offers removal alone.
 */

import * as React from 'react';
import { toast } from 'sonner';

import { Send, Smartphone, Trash2 } from '@/lib/icons';
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
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type {
  NtfyActionResult,
  NtfyContent,
  NtfyOutcome,
  NtfySubscriptionChange,
  NtfySubscriptionView,
} from '@/hooks/useNtfySubscriptions';
import { formatDate } from '@/lib/format';
import { outcomeKey, refusalKey } from './ntfy-labels';

interface NtfySubscriptionRowProps {
  lng: Language;
  subscription: NtfySubscriptionView;
  onUpdate: (
    id: string,
    change: NtfySubscriptionChange
  ) => Promise<NtfyActionResult<NtfySubscriptionView>>;
  onTest: (id: string) => Promise<NtfyActionResult<NtfyOutcome>>;
  onRemove: (id: string) => Promise<NtfyActionResult>;
  onSubscribeDevice: (subscription: NtfySubscriptionView) => void;
}

/** The content a select's value names; anything else reads as the safe default. */
function contentOf(value: string): NtfyContent {
  return value === 'full' ? 'full' : 'minimal';
}

/** The host a custom server is named by; the address itself if it cannot be read. */
function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function NtfySubscriptionRow({
  lng,
  subscription,
  onUpdate,
  onTest,
  onRemove,
  onSubscribeDevice,
}: NtfySubscriptionRowProps) {
  const { t } = useTranslation(lng);
  // The change being saved, shown until the list is read again: a control never snaps back to
  // the value the server held before the person's own choice.
  const [pending, setPending] = React.useState<NtfySubscriptionChange | null>(null);
  const [testing, setTesting] = React.useState(false);
  const [removing, setRemoving] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const helpId = React.useId();
  const activeId = React.useId();

  const name =
    subscription.server_kind === 'instance'
      ? t('settings.notifications.ntfy.server_instance')
      : hostOf(subscription.server_url);
  const readable = subscription.topic !== null;
  const saving = pending !== null;
  const content = pending?.content ?? subscription.content;
  const active = pending?.is_active ?? subscription.is_active;

  async function change(patch: NtfySubscriptionChange) {
    if (saving) return;
    setPending(patch);
    // Resolves once the list was read again, so the shown value is the server's own.
    const result = await onUpdate(subscription.id, patch);
    setPending(null);
    if (!result.ok) toast.error(t(refusalKey(result.errorCode)));
  }

  async function sendTest() {
    if (testing) return;
    setTesting(true);
    const result = await onTest(subscription.id);
    setTesting(false);
    if (!result.ok) {
      toast.error(t(refusalKey(result.errorCode)));
    } else if (result.data === 'sent') {
      toast.success(t('settings.notifications.ntfy.test_sent'));
    } else {
      toast.error(
        t('settings.notifications.ntfy.test_failed', { reason: t(outcomeKey(result.data ?? '')) })
      );
    }
  }

  async function confirmRemoval() {
    setRemoving(true);
    const result = await onRemove(subscription.id);
    setRemoving(false);
    if (result.ok) toast.success(t('settings.notifications.ntfy.removed'));
    else toast.error(t(refusalKey(result.errorCode)));
  }

  const actions: RowAction[] = [
    ...(readable
      ? [
          {
            key: 'test',
            label: t('settings.notifications.ntfy.test'),
            icon: Send,
            onSelect: () => void sendTest(),
            loading: testing,
          },
          {
            key: 'device',
            label: t('settings.notifications.ntfy.subscribe'),
            icon: Smartphone,
            onSelect: () => onSubscribeDevice(subscription),
          },
        ]
      : []),
    {
      key: 'remove',
      label: t('settings.notifications.ntfy.remove'),
      icon: Trash2,
      tone: 'destructive',
      onSelect: () => setConfirming(true),
      loading: removing,
    },
  ];

  return (
    <li className="space-y-3 rounded-lg border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium wrap-anywhere">{name}</p>
          {!active && <Badge variant="secondary">{t('settings.notifications.ntfy.paused')}</Badge>}
        </div>
        <RowActions
          actions={actions}
          menuLabel={t('settings.notifications.ntfy.actions', { name })}
        />
      </div>

      <StatusLine lng={lng} subscription={subscription} />

      {readable && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor={activeId} className="text-sm">
              {t('settings.notifications.ntfy.active_label')}
            </Label>
            <Switch
              id={activeId}
              checked={active}
              busy={saving}
              onCheckedChange={checked => void change({ is_active: checked })}
            />
          </div>
          <div className="space-y-1">
            <NativeSelect
              label={t('settings.notifications.ntfy.content_label')}
              aria-describedby={helpId}
              value={content}
              aria-busy={saving || undefined}
              onChange={event => void change({ content: contentOf(event.target.value) })}
            >
              <option value="minimal">{t('settings.notifications.ntfy.content_minimal')}</option>
              <option value="full">{t('settings.notifications.ntfy.content_full')}</option>
            </NativeSelect>
            <p id={helpId} className="text-xs text-muted-foreground">
              {content === 'full'
                ? t('settings.notifications.ntfy.content_full_help')
                : t('settings.notifications.ntfy.content_minimal_help')}
            </p>
          </div>
        </div>
      )}

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.notifications.ntfy.remove_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.notifications.ntfy.remove_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmRemoval()}>
              {t('settings.notifications.ntfy.remove')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}

/** How the last publication went, or why the subscription can only be removed. */
function StatusLine({ lng, subscription }: { lng: Language; subscription: NtfySubscriptionView }) {
  const { t } = useTranslation(lng);
  if (subscription.topic === null) {
    return <p className="text-xs text-warning">{t('settings.notifications.ntfy.unreadable')}</p>;
  }
  if (subscription.last_error_code) {
    return (
      <p className="text-xs text-destructive">
        {t('settings.notifications.ntfy.last_error', {
          reason: t(outcomeKey(subscription.last_error_code)),
        })}
      </p>
    );
  }
  if (subscription.last_sent_at) {
    return (
      <p className="text-xs text-muted-foreground">
        {t('settings.notifications.ntfy.last_sent', {
          when: formatDate(subscription.last_sent_at, lng, {
            dateStyle: 'medium',
            timeStyle: 'short',
          }),
        })}
      </p>
    );
  }
  return null;
}
