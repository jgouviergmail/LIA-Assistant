import { z } from '@/lib/zod';
const json = z.json();
export type SmsJson = z.infer<typeof json>;
export const smsOperationSchema = z.enum([
  'sms_token.create',
  'sms_token.revoke',
  'sms_preferences.update',
  'sms_sender_block.update',
  'sms_messages.delete',
]);
export type SmsOperation = z.infer<typeof smsOperationSchema>;
export const smsProposalSchema = z
  .object({
    command_id: z.string().uuid(),
    operation_id: smsOperationSchema,
    content_digest: z.string().regex(/^[0-9a-f]{64}$/),
    before: z.record(z.string(), json),
    after: z.record(z.string(), json),
    expires_at: z.string().datetime({ offset: true }),
  })
  .strict();
export type SmsProposal = z.infer<typeof smsProposalSchema>;
export const smsCompletionSchema = z.object({
  outcome: z.object({
    success: z.literal(true),
    committed: z.literal(true),
    phase: z.literal('committed'),
  }),
  secret: z.object({ token: z.string().startsWith('pi_') }).nullable(),
});
export interface SmsPreferences {
  ingestion_enabled: boolean;
  assistant_enabled: boolean;
  push_enabled: boolean;
}
export interface SmsSettings {
  preferences: SmsPreferences;
  usage: {
    message_count: number;
    receipt_count: number;
    logical_bytes: number;
    max_logical_bytes: number;
    max_receipts: number;
    last_received_at: string | null;
  };
  device_deliveries: Record<
    'pending' | 'sending' | 'sent' | 'failed' | 'unknown' | 'cancelled',
    number
  >;
}
export interface IngestionToken {
  id: string;
  source_id: string;
  resource: 'sms';
  label: string | null;
  token_prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
export interface SmsTokenPage {
  tokens: IngestionToken[];
  total: number;
  as_of: string;
  next_cursor: string | null;
}
export interface SmsBlockPage {
  blocks: { id: string; sender: string; created_at: string }[];
  total: number;
  as_of: string;
  next_cursor: string | null;
}
export interface SmsMessage {
  id: string;
  sender: string;
  display_name: string;
  identity_source: 'contact' | 'relation' | 'raw';
  identity_state: string;
  relation_key: string | null;
  body: string;
  received_at: string;
  date_kind: string;
  origin: string;
}
export interface SmsPage {
  items: SmsMessage[];
  total: number;
  as_of: string;
  revision: number;
  next_cursor: string | null;
}
export interface SmsSender {
  id: string;
  sender: string;
  display_name: string;
  identity_source: 'contact' | 'relation' | 'raw';
  identity_state: string;
  relation_key: string | null;
  total: number;
  latest_at: string;
}
export interface SmsSenderPage {
  items: SmsSender[];
  total: number;
  as_of: string;
  revision: number;
  next_cursor: string | null;
}
export interface SmsQuery {
  query?: string;
  sender_id?: string;
  from_ts?: string;
  to_ts?: string;
  limit?: number;
  cursor?: string;
}
