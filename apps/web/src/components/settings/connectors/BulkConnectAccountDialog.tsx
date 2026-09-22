'use client';

import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import type { KnownOAuthAccount } from './hooks/useBulkConnect';

interface Props {
  open: boolean;
  provider: 'google' | 'microsoft' | null;
  accounts: KnownOAuthAccount[];
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (grantId: string | null) => void;
  t: (key: string) => string;
}

const OTHER_ACCOUNT = '__other_account__';

/** Explicit account choice before adding several services to one provider grant. */
export function BulkConnectAccountDialog({
  open, provider, accounts, busy, onOpenChange, onSubmit, t,
}: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const groupName = useId();

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) setSelected(null);
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90dvh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t(`settings.connectors.bulk_connect.${provider ?? 'google'}_title`)}</DialogTitle>
          <DialogDescription>{t('settings.connectors.bulk_connect.description')}</DialogDescription>
        </DialogHeader>
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-medium">
            {t('settings.connectors.bulk_connect.account_label')}
          </legend>
          {accounts.map(account => (
            <label htmlFor={`${groupName}-${account.grantId}`} key={account.grantId} className="flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border p-3">
              <input
                id={`${groupName}-${account.grantId}`}
                type="radio" name={groupName} value={account.grantId}
                aria-label={account.email || t('settings.connectors.bulk_connect.unknown_account')}
                checked={selected === account.grantId} disabled={busy}
                onChange={() => setSelected(account.grantId)}
                className="size-4 shrink-0 accent-primary"
              />
              <span className="min-w-0 break-all text-sm">
                {account.email || t('settings.connectors.bulk_connect.unknown_account')}
              </span>
            </label>
          ))}
          <label htmlFor={`${groupName}-${OTHER_ACCOUNT}`} className="flex cursor-pointer items-center gap-3 rounded-lg border p-3">
            <input
              id={`${groupName}-${OTHER_ACCOUNT}`}
              type="radio" name={groupName} value={OTHER_ACCOUNT}
              aria-label={t('settings.connectors.bulk_connect.other_account')}
              checked={selected === OTHER_ACCOUNT} disabled={busy}
              onChange={() => setSelected(OTHER_ACCOUNT)}
              className="size-4 shrink-0 accent-primary"
            />
            <span className="text-sm">{t('settings.connectors.bulk_connect.other_account')}</span>
          </label>
        </fieldset>
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => handleOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button disabled={busy || selected === null}
            onClick={() => onSubmit(selected === OTHER_ACCOUNT ? null : selected)}>
            {t('settings.connectors.bulk_connect.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
