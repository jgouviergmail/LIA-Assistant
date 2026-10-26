/** Private HTTP projections and immutable human send intents. */
import { z } from '@/lib/zod';
import {
  literalMessageText as literalText,
  prepareMessageMetadata as prepareMetadata,
  type MailboxScope,
  type ServerClock,
} from './message-input';
import {
  readPublicFields,
  type PublicMessageWrite,
  type PublicMailboxFields,
} from './public-message-protocol';
export type { MailboxScope, ServerClock } from './message-input';
import { languages } from '@/i18n/settings';

const language = z.enum(languages).or(z.literal('zh-CN'));
const uuid = z.uuid();
const finite = z.number().finite();
const literal = (maximum: number) =>
  z
    .string()
    .max(maximum * 2)
    .refine(text => literalText(text, maximum) !== null);
const receipt = z
  .object({
    run_id: z.string().max(64),
    tokens_in: finite.int().nonnegative(),
    tokens_out: finite.int().nonnegative(),
    cost_eur: finite.nonnegative().nullable(),
  })
  .strict();
const message = z
  .object({
    id: uuid,
    sender_id: uuid,
    sender_alias: z.string().min(1).max(96),
    recipient_id: uuid,
    recipient_alias: z.string().min(1).max(96),
    outgoing: z.boolean(),
    original: literal(1000),
    text: literal(3000).nullable(),
    language,
    status: z.enum(['original', 'pending', 'translated', 'failed', 'uncertain', 'unavailable']),
    created_at: finite.nonnegative(),
    expires_at: finite.nonnegative(),
    receipt: receipt.nullable(),
  })
  .strict();
const mailbox = z
  .object({
    server_time: finite.nonnegative(),
    ttl_seconds: finite.int().positive().max(3600),
    messages: z.array(message).max(50),
    truncated: z.boolean(),
  })
  .strict();
export const messageAck = z
  .object({ id: uuid, status: z.enum(['delivered', 'pending', 'uncertain']) })
  .strict();
export type WorldMessage = z.infer<typeof message>;
export type WorldMailbox = z.infer<typeof mailbox> & PublicMailboxFields;
export interface PrivateMessageWrite extends MailboxScope {
  id: string;
  recipient: string;
  created_at: number;
  text: string;
  translation_consent: boolean;
}
export type MessageWrite = PrivateMessageWrite | PublicMessageWrite;
export interface TranslationWrite extends MailboxScope {
  id: string;
  message_id: string;
  created_at: number;
  translation_consent: true;
}

export function messageText(value: string): string | null {
  return literalText(value, 1000);
}

export function readMailbox(value: unknown): WorldMailbox {
  try {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    if (new TextEncoder().encode(JSON.stringify(value)).length > 200 * 1024) throw new Error();
    const data: Record<string, unknown> = { ...value };
    const publicFields = readPublicFields(data);
    for (const key of ['public_messages', 'public_available', 'public_truncated']) delete data[key];
    if (new TextEncoder().encode(JSON.stringify(data)).length > 132 * 1024) throw new Error();
    const result = mailbox.safeParse(data);
    if (result.success) return { ...result.data, ...publicFields };
  } catch {
    /* Neither a malformed payload nor a validation error may echo private text. */
  }
  throw new Error('world_mailbox_invalid');
}

export function prepareMessage(
  scope: MailboxScope,
  recipient: string,
  raw: string,
  consent: boolean,
  clock: ServerClock,
  now = performance.now()
): Readonly<PrivateMessageWrite> {
  const metadata = prepareMetadata(scope, clock, now);
  const text = messageText(raw);
  if (!text || !uuid.safeParse(recipient).success) throw new Error('world_message_input');
  return Object.freeze({ ...metadata, recipient, text, translation_consent: consent });
}

export function prepareTranslation(
  scope: MailboxScope,
  messageId: string,
  consent: boolean,
  clock: ServerClock,
  now = performance.now()
): Readonly<TranslationWrite> {
  if (!consent || !uuid.safeParse(messageId).success) throw new Error('world_translation_consent');
  const prepared: TranslationWrite = {
    ...prepareMetadata(scope, clock, now),
    message_id: messageId,
    translation_consent: true,
  };
  return Object.freeze(prepared);
}
