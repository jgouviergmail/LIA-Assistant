'use client';
import { useState } from 'react';
import { Archive } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { ListControls, ListField } from '@/components/ui/list-toolbar';
import { civilDateInstant } from '@/lib/civil-date-instant';
import type { useSmsManagement } from '@/hooks/useSmsManagement';

/**
 * Erasing SMS by period (the account's own days, the first included, the last
 * excluded) or all of them: each a reviewed command, confirmed in
 * `SmsConfirmation`. A period that does not move forward is refused here.
 */
export function SmsArchiveErasure({
  actions,
  timezone,
}: {
  actions: ReturnType<typeof useSmsManagement>;
  timezone: string;
}) {
  const { t } = useTranslation();
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [invalid, setInvalid] = useState(false);
  function eraseRange() {
    try {
      if ((!from && !to) || (from && to && from >= to)) throw new RangeError();
      const scope = {
        ...(from ? { from_ts: civilDateInstant(from, timezone) } : {}),
        ...(to ? { to_ts: civilDateInstant(to, timezone) } : {}),
      };
      setInvalid(false);
      void actions.propose('sms_messages.delete', scope);
    } catch {
      setInvalid(true);
    }
  }
  return (
    <Disclosure icon={Archive} title={t('sms.management')}>
      <div className="space-y-4 pt-2">
        <p className="text-sm text-muted-foreground">{t('sms.retention')}</p>
        <form
          className="space-y-3"
          onSubmit={event => {
            event.preventDefault();
            eraseRange();
          }}
        >
          <ListControls>
            <ListField htmlFor="sms-erase-from" label={t('sms.from')}>
              <Input
                id="sms-erase-from"
                type="date"
                className="h-11"
                value={from}
                onChange={event => setFrom(event.target.value)}
              />
            </ListField>
            <ListField htmlFor="sms-erase-to" label={t('sms.to')}>
              <Input
                id="sms-erase-to"
                type="date"
                className="h-11"
                value={to}
                onChange={event => setTo(event.target.value)}
              />
            </ListField>
          </ListControls>
          {invalid && (
            <p role="alert" className="text-sm text-destructive">
              {t('common.error')}
            </p>
          )}
          <Button type="submit" variant="outline" aria-disabled={actions.busy || (!from && !to)}>
            {t('sms.erase_range')}
          </Button>
        </form>
        <Button
          variant="destructive"
          aria-disabled={actions.busy}
          onClick={() => {
            void actions.propose('sms_messages.delete', { all_messages: true });
          }}
        >
          {t('sms.erase_all')}
        </Button>
      </div>
    </Disclosure>
  );
}
