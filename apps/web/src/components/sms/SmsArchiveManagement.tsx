'use client';
import { useState } from 'react';
import { Archive, ShieldBan, UnlockKeyhole } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import { civilDateInstant } from '@/lib/civil-date-instant';
import type { useSmsSettings } from '@/hooks/useSmsSettings';
import type { useSmsManagement } from '@/hooks/useSmsManagement';

export function SmsArchiveManagement({
  data,
  actions,
  timezone,
}: {
  data: ReturnType<typeof useSmsSettings>;
  actions: ReturnType<typeof useSmsManagement>;
  timezone: string;
}) {
  const { t } = useTranslation();
  const [sender, setSender] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [invalid, setInvalid] = useState(false);
  const blocks = data.blocks.data;
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
    <>
      <Disclosure icon={ShieldBan} title={t('sms.blocked')} surface="nested">
        <div className="space-y-4 pt-2">
          <form
            className="space-y-2"
            onSubmit={event => {
              event.preventDefault();
              if (sender.trim())
                void actions.propose('sms_sender_block.update', { sender, blocked: true });
            }}
          >
            <Label htmlFor="sms-block-sender">{t('sms.block_sender')}</Label>
            <div className="flex flex-wrap gap-2">
              <div className="min-w-0 flex-1">
                <Input
                  id="sms-block-sender"
                  value={sender}
                  maxLength={256}
                  onChange={event => setSender(event.target.value)}
                />
              </div>
              <Button type="submit" aria-disabled={actions.busy || !sender.trim()}>
                {t('sms.block')}
              </Button>
            </div>
          </form>
          <ul className="space-y-2">
            {blocks?.blocks.map(block => (
              <li key={block.id} className="flex items-center gap-3 rounded-lg border p-3">
                <span className="min-w-0 flex-1 break-words text-sm">{block.sender}</span>
                <RowActions
                  menuLabel={`${t('common.actions')} · ${block.sender}`}
                  actions={[
                    {
                      key: 'unblock',
                      icon: UnlockKeyhole,
                      label: t('sms.unblock'),
                      blocked: actions.busy,
                      onSelect: () => {
                        void actions.propose('sms_sender_block.update', {
                          sender: block.sender,
                          blocked: false,
                        });
                      },
                    },
                  ]}
                />
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            {data.blockCursor && (
              <Button variant="outline" onClick={() => data.setBlockCursor(undefined)}>
                {t('common.previous')}
              </Button>
            )}
            {blocks?.next_cursor && (
              <Button
                variant="outline"
                onClick={() => {
                  if (blocks.next_cursor)
                    data.setBlockCursor({ after_id: blocks.next_cursor, as_of: blocks.as_of });
                }}
              >
                {t('sms.load_more')}
              </Button>
            )}
          </div>
        </div>
      </Disclosure>
      <Disclosure icon={Archive} title={t('sms.management')} surface="nested">
        <div className="space-y-4 pt-2">
          <p className="text-sm text-muted-foreground">{t('sms.retention')}</p>
          <form
            className="space-y-3"
            onSubmit={event => {
              event.preventDefault();
              eraseRange();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="sms-erase-from">
                  {t('sms.from')} · {timezone}
                </Label>
                <Input
                  id="sms-erase-from"
                  type="date"
                  value={from}
                  onChange={event => setFrom(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sms-erase-to">
                  {t('sms.to')} · {timezone}
                </Label>
                <Input
                  id="sms-erase-to"
                  type="date"
                  value={to}
                  onChange={event => setTo(event.target.value)}
                />
              </div>
            </div>
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
    </>
  );
}
