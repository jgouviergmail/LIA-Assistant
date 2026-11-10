/** The only browser address builder for a server-verified card item. */
import { z } from '@/lib/zod';
import type { Language } from '@/i18n/settings';
import { toolHref } from './search';
import type { WorkbenchToolId } from './types';
import { CARD_SOURCE_PARAM } from './card-source';

const kindSchema = z.enum(['email', 'event', 'calendar', 'contact', 'task', 'file', 'hue_light']);
export type CardTargetKind = z.infer<typeof kindSchema>;
const identifier = z.string().min(1);
const targetSchema = z.object({
  kind: kindSchema,
  item_id: identifier,
  container_id: identifier.nullable(),
  day: z.iso.date().nullable(),
  is_folder: z.boolean(),
});
export type CardToolTarget = z.infer<typeof targetSchema>;
const cardTargetResponseSchema = z.object({
  available: z.boolean(),
  target: targetSchema.nullable(),
  reason: z.enum(['historical', 'source_changed', 'unavailable']).nullable(),
});

const TOOLS: Record<CardTargetKind, WorkbenchToolId> = {
  email: 'mail',
  event: 'calendar',
  calendar: 'calendar',
  contact: 'contacts',
  task: 'tasks',
  file: 'files',
  hue_light: 'lights',
};

/** A presentation hint selects a tool family, never an item or an authority. */
export function cardTargetKind(value: unknown): CardTargetKind | null {
  const parsed = kindSchema.safeParse(typeof value === 'string' ? value.toLowerCase() : value);
  return parsed.success ? parsed.data : null;
}

export function cardToolHref(kind: CardTargetKind, lng: Language): string {
  return toolHref(TOOLS[kind], lng);
}

const QUERIES: Record<CardTargetKind, (target: CardToolTarget) => Record<string, string> | null> = {
  email: target => ({
    id: target.item_id,
    ...(target.container_id ? { folder: target.container_id } : {}),
  }),
  event: target =>
    target.container_id
      ? {
          cal: target.container_id,
          event: target.item_id,
          ...(target.day ? { day: target.day } : {}),
        }
      : null,
  calendar: target => ({ cal: target.item_id }),
  contact: target => ({ contact: target.item_id }),
  task: target =>
    target.container_id ? { list: target.container_id, task: target.item_id } : null,
  file: target => ({ [target.is_folder ? 'folder' : 'file']: target.item_id }),
  hue_light: target => ({ light: target.item_id }),
};

/** A scoped item without its container opens nothing, never a guessed default. */
export function cardTargetHref(value: unknown, lng: Language, sourceToken: string): string | null {
  const parsed = targetSchema.safeParse(value);
  if (!parsed.success) return null;
  const target = parsed.data;
  const query = QUERIES[target.kind](target);
  if (!query || !sourceToken) return null;
  return `${cardToolHref(target.kind, lng)}?${new URLSearchParams({ ...query, [CARD_SOURCE_PARAM]: sourceToken })}`;
}

/** The wire verdict and its target form one decision; inconsistent or malformed data opens nothing. */
export function resolveCardTarget(response: unknown, lng: Language, sourceToken: string) {
  const parsed = cardTargetResponseSchema.safeParse(response);
  const value = parsed.success ? parsed.data : null;
  const href =
    value?.available && value.reason === null
      ? cardTargetHref(value.target, lng, sourceToken)
      : null;
  return { href, reason: value?.reason ?? ('unavailable' as const) };
}
