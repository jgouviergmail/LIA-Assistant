'use client';
import { useState, useSyncExternalStore } from 'react';
import { KeyRound, RotateCw, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { IngestionApiPanel } from '@/components/ingestion/IngestionApiPanel';
import { Disclosure } from '@/components/ui/disclosure';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import { apiEndpointUrl } from '@/lib/api-client';
import type { useSmsSettings } from '@/hooks/useSmsSettings';
import type { useSmsManagement } from '@/hooks/useSmsManagement';
const subscribe = () => () => {};
const serverOrigin = () => '';
const browserOrigin = () => window.location.origin;

export function SmsTokenSettings({
  data,
  actions,
}: {
  data: ReturnType<typeof useSmsSettings>;
  actions: ReturnType<typeof useSmsManagement>;
}) {
  const { t } = useTranslation();
  const [label, setLabel] = useState('');
  const origin = useSyncExternalStore(subscribe, browserOrigin, serverOrigin);
  const endpoint = apiEndpointUrl('/ingest/message');
  const url = endpoint.startsWith('http') ? endpoint : `${origin}${endpoint}`;
  const tokens = data.tokens.data;
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t('healthMetrics.tokens.copied'));
    } catch {
      toast.error(t('common.copyFailed'));
    }
  }
  return (
    <Disclosure icon={KeyRound} title={t('sms.api')} surface="nested">
      <div className="space-y-4 pt-2">
        <IngestionApiPanel
          endpoints={[
            { id: 'sms-ingestion-url', label: t('sms.url'), url, hint: t('sms.payload') },
          ]}
          labels={{
            copy: t('common.copy'),
            close: t('common.close'),
            show: t('common.show'),
            hide: t('common.hide'),
            secret: t('healthMetrics.tokens.justCreated'),
          }}
          secret={actions.secret}
          onClearSecret={actions.clearSecret}
          onCopy={value => {
            void copy(value);
          }}
        />
        <form
          className="space-y-2"
          onSubmit={event => {
            event.preventDefault();
            void actions.propose('sms_token.create', { label: label.trim() || 'iPhone' });
          }}
        >
          <Label htmlFor="sms-source-label">{t('sms.token_label')}</Label>
          <div className="flex min-w-0 flex-wrap gap-2">
            <div className="min-w-0 flex-1">
              <Input
                id="sms-source-label"
                value={label}
                maxLength={128}
                onChange={event => setLabel(event.target.value)}
              />
            </div>
            <Button type="submit" aria-disabled={actions.busy}>
              {t('sms.create_token')}
            </Button>
          </div>
        </form>
        <h4 className="text-sm font-medium">{t('sms.tokens')}</h4>
        {tokens?.tokens.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('sms.no_tokens')}</p>
        )}
        <ul className="space-y-2">
          {tokens?.tokens.map(token => (
            <li key={token.id} className="flex min-w-0 items-center gap-3 rounded-lg border p-3">
              <div className="min-w-0 flex-1">
                <p className="break-words text-sm font-medium">
                  {token.label || token.token_prefix}
                </p>
                <code className="break-all text-xs text-muted-foreground">
                  {token.token_prefix}…
                </code>
                {token.revoked_at && (
                  <p className="text-xs text-muted-foreground">{t('sms.revoked')}</p>
                )}
              </div>
              {!token.revoked_at && (
                <RowActions
                  menuLabel={`${t('common.actions')} · ${token.label || token.token_prefix}`}
                  actions={[
                    {
                      key: 'rotate',
                      label: t('sms.rotate'),
                      icon: RotateCw,
                      blocked: actions.busy,
                      onSelect: () => {
                        void actions.propose('sms_token.create', {
                          label: token.label || 'iPhone',
                          source_id: token.source_id,
                        });
                      },
                    },
                    {
                      key: 'revoke',
                      label: t('sms.revoke'),
                      icon: Trash2,
                      tone: 'destructive',
                      blocked: actions.busy,
                      onSelect: () => {
                        void actions.propose('sms_token.revoke', { token_id: token.id });
                      },
                    },
                  ]}
                />
              )}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          {data.tokenCursor && (
            <Button variant="outline" onClick={() => data.setTokenCursor(undefined)}>
              {t('common.previous')}
            </Button>
          )}
          {tokens?.next_cursor && (
            <Button
              variant="outline"
              onClick={() => {
                if (tokens.next_cursor)
                  data.setTokenCursor({ after_id: tokens.next_cursor, as_of: tokens.as_of });
              }}
            >
              {t('sms.load_more')}
            </Button>
          )}
        </div>
      </div>
    </Disclosure>
  );
}
