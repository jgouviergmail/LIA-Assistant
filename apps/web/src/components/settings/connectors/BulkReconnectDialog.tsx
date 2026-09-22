'use client';

import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import type { Connector } from './types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  provider: 'google' | 'microsoft';
  connectors: Connector[];
  busy: boolean;
  onSubmit: (types: string[]) => void;
  t: (key: string) => string;
}

function labelFor(type: string): string {
  if (type === 'gmail') return 'Gmail';
  return isValidConnectorType(type) ? CONNECTOR_LABELS[type] : type;
}

/** Explicitly chooses which logical services may share one provider account. */
export function BulkReconnectDialog({
  open,
  onOpenChange,
  provider,
  connectors,
  busy,
  onSubmit,
  t,
}: Props) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const idPrefix = useId();
  const selectedGrant = connectors.find(
    connector => selectedIds.includes(connector.id) && connector.oauth_grant_id
  )?.oauth_grant_id;
  const selectedTypes = connectors
    .filter(connector => selectedIds.includes(connector.id))
    .map(connector => connector.connector_type);

  const toggle = (id: string, checked: boolean) => {
    setSelectedIds(previous =>
      checked ? [...previous, id] : previous.filter(selected => selected !== id)
    );
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) setSelectedIds([]);
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90dvh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t(`settings.connectors.bulk_reconnect.${provider}_title`)}</DialogTitle>
          <DialogDescription>{t('settings.connectors.bulk_reconnect.description')}</DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {t('settings.connectors.bulk_reconnect.account_warning')}
        </p>
        <div className="space-y-2">
          {connectors.map(connector => {
            const disabled = Boolean(
              busy ||
                (selectedGrant &&
                  connector.oauth_grant_id &&
                  connector.oauth_grant_id !== selectedGrant)
            );
            const email = connector.metadata?.oauth_account_email;
            return (
              <label
                key={connector.id}
                htmlFor={`${idPrefix}-${connector.id}`}
                className="flex min-w-0 cursor-pointer items-start gap-3 rounded-lg border p-3 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60"
              >
                <Checkbox
                  id={`${idPrefix}-${connector.id}`}
                  checked={selectedIds.includes(connector.id)}
                  disabled={disabled}
                  onChange={event => toggle(connector.id, event.target.checked)}
                  className="mt-0.5"
                />
                <span className="min-w-0 text-sm">
                  <span className="block font-medium">{labelFor(connector.connector_type)}</span>
                  <span className="block break-all text-muted-foreground">
                    {email || t('settings.connectors.bulk_reconnect.unknown_account')}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button disabled={busy || selectedTypes.length === 0} onClick={() => onSubmit(selectedTypes)}>
            {t('settings.connectors.bulk_reconnect.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
