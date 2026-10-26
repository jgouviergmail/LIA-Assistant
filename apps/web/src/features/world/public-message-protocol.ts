/** Explicit public HTTP audience. PUBLIC_THREAD is a UI key and never a wire recipient. */
import { z } from '@/lib/zod';
import { languages } from '@/i18n/settings';
import {
  literalMessageText,
  prepareMessageMetadata,
  type MailboxScope,
  type ServerClock,
} from './message-input';
export const PUBLIC_THREAD = '@public';
export const PUBLIC_MESSAGE_CHARS = 240;
const literal = (maximum: number) =>
  z
    .string()
    .max(maximum * 2)
    .refine(text => literalMessageText(text, maximum) !== null);
const finite = z.number().finite();
const receipt = z
  .object({
    run_id: z.string().max(64),
    tokens_in: finite.int().nonnegative(),
    tokens_out: finite.int().nonnegative(),
    cost_eur: finite.nonnegative().nullable(),
  })
  .strict();
const publicMessage = z
  .object({
    audience: z.literal('public'),
    id: z.uuid(),
    sender_id: z.uuid(),
    sender_alias: z.string().min(1).max(96),
    outgoing: z.boolean(),
    original: literal(PUBLIC_MESSAGE_CHARS),
    text: literal(720).nullable(),
    language: z.enum(languages).or(z.literal('zh-CN')),
    status: z.enum(['original', 'pending', 'translated', 'failed', 'uncertain', 'unavailable']),
    created_at: finite.nonnegative(),
    expires_at: finite.nonnegative(),
    receipt: receipt.nullable(),
  })
  .strict();
const publicPart = z
  .object({
    public_available: z.boolean(),
    public_messages: z.array(publicMessage).max(50),
    public_truncated: z.boolean(),
  })
  .strict();
export type WorldPublicMessage = z.infer<typeof publicMessage>;
export interface PublicMailboxFields {
  public_available?: boolean;
  public_messages?: WorldPublicMessage[];
  public_truncated?: boolean;
}
export interface PublicMessageWrite extends MailboxScope {
  audience: 'public';
  id: string;
  created_at: number;
  text: string;
  translation_consent: boolean;
}
export function publicMessageText(value: string): string | null {
  return literalMessageText(value, PUBLIC_MESSAGE_CHARS);
}
export function preparePublicMessage(
  scope: MailboxScope,
  raw: string,
  consent: boolean,
  clock: ServerClock,
  now = performance.now()
): Readonly<PublicMessageWrite> {
  const text = publicMessageText(raw);
  if (!text) throw new Error('world_message_input');
  return Object.freeze({
    ...prepareMessageMetadata(scope, clock, now),
    audience: 'public',
    text,
    translation_consent: consent,
  });
}
export function readPublicFields(value: Record<string, unknown>): PublicMailboxFields {
  if (
    !['public_messages', 'public_available', 'public_truncated'].some(key =>
      Object.hasOwn(value, key)
    )
  )
    return {};
  const part = {
    public_messages: value.public_messages,
    public_available: value.public_available,
    public_truncated: value.public_truncated,
  };
  const parsed = publicPart.safeParse(part);
  if (
    parsed.success &&
    parsed.data.public_available &&
    new TextEncoder().encode(JSON.stringify(part)).length <= 66 * 1024
  )
    return parsed.data;
  return { public_available: false, public_messages: [], public_truncated: false };
}
