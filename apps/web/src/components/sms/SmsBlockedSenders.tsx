'use client';
import { useState } from 'react';
import { ShieldBan, UnlockKeyhole } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import type { useSmsBlockedSenders } from '@/hooks/useSmsBlockedSenders';
import type { useSmsManagement } from '@/hooks/useSmsManagement';

/**
 * The senders whose next SMS are refused, a page at a time: blocking and
 * unblocking are reviewed commands, confirmed in `SmsConfirmation`.
 */
export function SmsBlockedSenders({
  blocked,
  actions,
}: {
  blocked: ReturnType<typeof useSmsBlockedSenders>;
  actions: ReturnType<typeof useSmsManagement>;
}) {
  const { t } = useTranslation();
  const [sender, setSender] = useState('');
  const page = blocked.blocks.data;
  return (
    <Disclosure icon={ShieldBan} title={t('sms.blocked')}>
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
            {/* The field asks 14rem before sharing its line (owner request 2026-11-08): on a
                phone the long button goes under it instead of squeezing it to a stub. */}
            <div className="min-w-0 flex-[1_1_14rem]">
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
          {page?.blocks.map(block => (
            <li
              key={block.id}
              className="flex items-center gap-3 rounded-lg border bg-background p-3"
            >
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
          {blocked.cursor && (
            <Button variant="outline" onClick={() => blocked.setCursor(undefined)}>
              {t('common.previous')}
            </Button>
          )}
          {page?.next_cursor && (
            <Button
              variant="outline"
              onClick={() => {
                if (page.next_cursor)
                  blocked.setCursor({ after_id: page.next_cursor, as_of: page.as_of });
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
