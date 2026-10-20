'use client';
import { useTranslation } from 'react-i18next';
import { z } from '@/lib/zod';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { useSmsManagement } from '@/hooks/useSmsManagement';
import type { SmsJson } from '@/types/sms';

const preferences = z.object({
  ingestion_enabled: z.boolean(),
  assistant_enabled: z.boolean(),
  push_enabled: z.boolean(),
});
const token = z.object({ label: z.string().nullable(), token_prefix: z.string(), id: z.string() });
const creation = z.object({ label: z.string(), source_id: z.string().nullable() });
const block = z.object({ sender: z.string(), blocked: z.boolean() });
const erasure = z.object({
  count: z.number(),
  from_ts: z.string().nullable(),
  to_ts: z.string().nullable(),
  all_messages: z.boolean(),
  sender_id: z.string().nullable(),
  message_ids: z.array(z.string()),
});
type Line = { label: string; value: string | number | boolean };
function rows(value: Record<string, SmsJson>): Line[] {
  const prefs = preferences.safeParse(value.sms_preferences);
  if (prefs.success)
    return [
      { label: 'ingestion', value: prefs.data.ingestion_enabled },
      { label: 'assistant', value: prefs.data.assistant_enabled },
      { label: 'push', value: prefs.data.push_enabled },
    ];
  const created = creation.safeParse(value.ingestion_token_to_create);
  if (created.success)
    return [
      { label: 'token_label', value: created.data.label },
      ...(created.data.source_id ? [{ label: 'tokens', value: created.data.source_id }] : []),
    ];
  const revoked = token.safeParse(value.ingestion_token_to_revoke);
  if (revoked.success)
    return [
      {
        label: 'tokens',
        value: `${revoked.data.label ?? ''} · ${revoked.data.token_prefix}… · ${revoked.data.id}`,
      },
    ];
  const sender = block.safeParse(value.sms_sender_block);
  if (sender.success)
    return [
      { label: 'block_sender', value: sender.data.sender },
      { label: 'blocked', value: sender.data.blocked },
    ];
  const erased = erasure.safeParse(value.sms_messages_to_delete);
  if (erased.success)
    return [
      { label: 'management', value: erased.data.count },
      { label: 'erase_all', value: erased.data.all_messages },
      { label: 'from', value: erased.data.from_ts ?? '—' },
      { label: 'to', value: erased.data.to_ts ?? '—' },
      ...(erased.data.sender_id ? [{ label: 'by_sender', value: erased.data.sender_id }] : []),
      ...erased.data.message_ids.map(id => ({ label: 'title', value: id })),
    ];
  return [];
}
function Scope({ value }: { value: Record<string, SmsJson> }) {
  const { t } = useTranslation();
  const values = rows(value);
  return values.length ? (
    <dl className="space-y-2 text-sm">
      {values.map((line, index) => (
        <div key={`${line.label}:${index}`}>
          <dt className="text-muted-foreground">{t(`sms.${line.label}`)}</dt>
          <dd className="whitespace-pre-wrap break-words">
            {typeof line.value === 'boolean' ? t(`sms.${line.value ? 'on' : 'off'}`) : line.value}
          </dd>
        </div>
      ))}
    </dl>
  ) : (
    <p>—</p>
  );
}
export function SmsConfirmation({ actions }: { actions: ReturnType<typeof useSmsManagement> }) {
  const { t } = useTranslation();
  const proposal = actions.proposal;
  return (
    <AlertDialog
      open={proposal !== null}
      onOpenChange={open => {
        if (!open) void actions.cancel();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('sms.review')}</AlertDialogTitle>
          <AlertDialogDescription>
            {proposal?.operation_id === 'sms_messages.delete'
              ? t('sms.retention')
              : proposal?.operation_id === 'sms_token.create'
                ? t('healthMetrics.tokens.justCreated')
                : t('sms.review')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {proposal && (
          <div className="grid min-w-0 gap-4 sm:grid-cols-2">
            <section className="min-w-0">
              <h3 className="mb-2 font-medium">{t('sms.before')}</h3>
              <Scope value={proposal.before} />
            </section>
            <section className="min-w-0">
              <h3 className="mb-2 font-medium">{t('sms.after')}</h3>
              <Scope value={proposal.after} />
            </section>
          </div>
        )}
        <AlertDialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              void actions.cancel();
            }}
          >
            {t('common.cancel')}
          </Button>
          <Button
            variant={proposal?.operation_id === 'sms_messages.delete' ? 'destructive' : 'default'}
            aria-disabled={actions.busy}
            onClick={() => {
              void actions.confirm();
            }}
          >
            {t('sms.confirm')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
