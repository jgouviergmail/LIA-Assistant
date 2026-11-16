'use client';

/**
 * The form that adds an ntfy subscription (ADR-391): on the instance's server — nothing to set,
 * LIA draws a private topic — or on another https server the person names, with an existing
 * topic and token of theirs or a drawn topic. What the notification shows is chosen here too,
 * the notice alone by default (owner decision 2026-11-16).
 *
 * A refusal keeps the form open and says, in words, what to correct; nothing the person typed is
 * lost. Only the choices the instance offers are shown.
 */

import * as React from 'react';

import { Eye, Server } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FormSection } from '@/components/ui/form-section';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type {
  NtfyActionResult,
  NtfyContent,
  NtfyOverview,
  NtfyServerKind,
  NtfySubscriptionInput,
  NtfySubscriptionView,
} from '@/hooks/useNtfySubscriptions';
import { refusalKey } from './ntfy-labels';

interface NtfySubscriptionDialogProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  overview: NtfyOverview;
  onCreate: (input: NtfySubscriptionInput) => Promise<NtfyActionResult<NtfySubscriptionView>>;
  onCreated: (created: NtfySubscriptionView) => void;
}

/** The request a filled form asks for: an instance subscription names nothing of its own. */
export function subscriptionInput(
  server: NtfyServerKind,
  fields: { serverUrl: string; topic: string; token: string },
  content: NtfyContent
): NtfySubscriptionInput {
  if (server === 'instance') return { server, content };
  const input: NtfySubscriptionInput = { server, server_url: fields.serverUrl.trim(), content };
  if (fields.topic.trim()) input.topic = fields.topic.trim();
  if (fields.token.trim()) input.token = fields.token.trim();
  return input;
}

export function NtfySubscriptionDialog({
  lng,
  open,
  onOpenChange,
  overview,
  onCreate,
  onCreated,
}: NtfySubscriptionDialogProps) {
  const { t } = useTranslation(lng);
  const instanceOffered = overview.instance_url !== null;
  const [server, setServer] = React.useState<NtfyServerKind>(
    instanceOffered ? 'instance' : 'custom'
  );
  const [fields, setFields] = React.useState({ serverUrl: '', topic: '', token: '' });
  const [content, setContent] = React.useState<NtfyContent>('minimal');
  const [refusal, setRefusal] = React.useState<{ code: string | null } | null>(null);
  const [saving, setSaving] = React.useState(false);

  function field(name: keyof typeof fields) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setFields(current => ({ ...current, [name]: event.target.value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setRefusal(null);
    const result = await onCreate(subscriptionInput(server, fields, content));
    setSaving(false);
    if (result.ok && result.data) {
      setFields({ serverUrl: '', topic: '', token: '' });
      setContent('minimal');
      onCreated(result.data);
    } else {
      setRefusal({ code: result.errorCode });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settings.notifications.ntfy.form.title')}</DialogTitle>
          <DialogDescription>{t('settings.notifications.ntfy.form.description')}</DialogDescription>
        </DialogHeader>

        <form className="space-y-6" onSubmit={event => void submit(event)}>
          <FormSection icon={Server} title={t('settings.notifications.ntfy.form.server_label')}>
            <div className="space-y-3">
              {instanceOffered && (
                <Choice
                  name="ntfy-server"
                  checked={server === 'instance'}
                  onSelect={() => setServer('instance')}
                  label={t('settings.notifications.ntfy.form.server_instance')}
                  help={t('settings.notifications.ntfy.form.server_instance_help')}
                />
              )}
              {overview.custom_servers_enabled && (
                <Choice
                  name="ntfy-server"
                  checked={server === 'custom'}
                  onSelect={() => setServer('custom')}
                  label={t('settings.notifications.ntfy.form.server_custom')}
                  help={t('settings.notifications.ntfy.form.server_custom_help')}
                />
              )}
            </div>
            {server === 'custom' && (
              <div className="space-y-4">
                <Input
                  label={t('settings.notifications.ntfy.form.server_url')}
                  type="url"
                  inputMode="url"
                  autoComplete="off"
                  placeholder="https://ntfy.sh"
                  required
                  maxLength={512}
                  value={fields.serverUrl}
                  onChange={field('serverUrl')}
                />
                <div className="space-y-1">
                  <Input
                    label={t('settings.notifications.ntfy.form.topic')}
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={64}
                    value={fields.topic}
                    onChange={field('topic')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('settings.notifications.ntfy.form.topic_help')}
                  </p>
                </div>
                <div className="space-y-1">
                  <Input
                    label={t('settings.notifications.ntfy.form.token')}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={64}
                    value={fields.token}
                    onChange={field('token')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('settings.notifications.ntfy.form.token_help')}
                  </p>
                </div>
              </div>
            )}
          </FormSection>

          <FormSection icon={Eye} title={t('settings.notifications.ntfy.content_label')}>
            <div className="space-y-3">
              <Choice
                name="ntfy-content"
                checked={content === 'minimal'}
                onSelect={() => setContent('minimal')}
                label={t('settings.notifications.ntfy.content_minimal')}
                help={t('settings.notifications.ntfy.content_minimal_help')}
              />
              <Choice
                name="ntfy-content"
                checked={content === 'full'}
                onSelect={() => setContent('full')}
                label={t('settings.notifications.ntfy.content_full')}
                help={t('settings.notifications.ntfy.content_full_help')}
              />
            </div>
          </FormSection>

          {refusal && (
            <p role="alert" className="text-sm text-destructive">
              {t(refusalKey(refusal.code), { max: overview.max_subscriptions })}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('settings.notifications.ntfy.form.cancel')}
            </Button>
            <Button type="submit" isLoading={saving}>
              {t('settings.notifications.ntfy.form.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** One radio choice with its explanation, the whole line clickable. */
function Choice({
  name,
  checked,
  onSelect,
  label,
  help,
}: {
  name: string;
  checked: boolean;
  onSelect: () => void;
  label: string;
  help: string;
}) {
  const labelId = React.useId();
  const helpId = React.useId();
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border bg-background p-3">
      <input
        type="radio"
        name={name}
        className="mt-1 h-4 w-4 shrink-0 accent-primary"
        checked={checked}
        onChange={onSelect}
        aria-labelledby={labelId}
        aria-describedby={helpId}
      />
      <span className="space-y-0.5">
        <span id={labelId} className="block text-sm font-medium">
          {label}
        </span>
        <span id={helpId} className="block text-xs text-muted-foreground">
          {help}
        </span>
      </span>
    </label>
  );
}
