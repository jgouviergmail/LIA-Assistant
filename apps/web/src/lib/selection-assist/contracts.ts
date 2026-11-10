/** Closed selection vocabulary and validation of the proposal crossing the API boundary. */
import { z } from '@/lib/zod';
import { MEMORY_CATEGORIES } from '@/hooks/useMemories';
import type { RecurrenceSpec } from '@/types/recurrence';

export const READ_ACTIONS = [
  'read',
  'ask',
  'explain',
  'summarize',
  'simplify',
  'translate',
  'internet',
  'task',
  'event',
  'reminder',
  'ticket',
  'memory',
  'lia',
] as const;
export const EDIT_ACTIONS = ['translate', 'fix', 'format', 'shorter', 'formal', 'warm'] as const;
export type SelectionAction = (typeof READ_ACTIONS)[number] | (typeof EDIT_ACTIONS)[number];
export type Destination = 'task' | 'event' | 'memory' | 'reminder' | 'ticket';
export type ModelSelectionAction = Exclude<SelectionAction, 'read' | 'lia'>;
export interface SelectionOffer {
  text_max_chars: number;
  question_max_chars: number;
  language_max_chars: number;
  internet_available: boolean;
  read_aloud_available: boolean;
  internet_timeout_seconds: number;
  call_timeout_seconds: number;
  heartbeat_seconds: number;
  destinations: Destination[];
}
export const selectionOfferSchema = z.object({
  text_max_chars: z.number().int().positive(),
  question_max_chars: z.number().int().positive(),
  language_max_chars: z.number().int().min(2),
  internet_available: z.boolean(),
  read_aloud_available: z.boolean(),
  internet_timeout_seconds: z.number().positive(),
  call_timeout_seconds: z.number().positive(),
  heartbeat_seconds: z.number().positive(),
  destinations: z.array(z.enum(['task', 'event', 'memory', 'reminder', 'ticket'])),
});
const text = z.string();
const usage = z.object({
  tokens_in: z.number().nonnegative(),
  tokens_out: z.number().nonnegative(),
  tokens_cache: z.number().nonnegative(),
  cost_eur: z.number().nonnegative(),
  model_name: text.nullable(),
});
const task = z.object({
  title: text.min(1),
  notes: text,
  due: text.nullable(),
  list_name: text.nullable(),
  importance: z.literal('high').nullable(),
});
const event = z.object({
  summary: text.min(1),
  start_date: text.nullable(),
  start_time: text.nullable(),
  end_date: text.nullable(),
  end_time: text.nullable(),
  all_day: z.boolean(),
  location: text,
  description: text,
  attendees: z.array(text),
  repeat: z.enum(['none', 'daily', 'weekly', 'monthly', 'yearly']),
  conference: z.boolean(),
});
const memory = z.object({
  content: text.min(1),
  category: z.enum(MEMORY_CATEGORIES),
  emotional_weight: z.number().optional(),
  trigger_topic: text.optional(),
  usage_nuance: text.optional(),
  importance: z.number().optional(),
});
const timeOfDay = z.object({
  hour: z.number().int().min(0).max(23),
  minute: z.number().int().min(0).max(59),
});
const recurrence = z.object({
  freq: z.enum(['once', 'daily', 'weekly', 'monthly', 'yearly']),
  anchor_date: z.iso.date(),
  interval: z.number().int().positive(),
  byweekday: z.array(z.number().int().min(1).max(7)),
  bymonthday: z.array(
    z
      .number()
      .int()
      .min(-1)
      .max(31)
      .refine(day => day !== 0)
  ),
  bymonth: z.array(z.number().int().min(1).max(12)),
  nth_weekday: z
    .tuple([
      z
        .number()
        .int()
        .min(-1)
        .max(5)
        .refine(n => n !== 0),
      z.number().int().min(1).max(7),
    ])
    .nullable(),
  times: z.object({
    mode: z.enum(['at', 'every']),
    at: z.array(timeOfDay),
    step_minutes: z.number().int().positive().nullable(),
    start: timeOfDay.nullable(),
    end: timeOfDay.nullable(),
  }),
  end: z.object({
    kind: z.enum(['never', 'on_date', 'after_count']),
    on_date: z.iso.date().nullable(),
    after_count: z.number().int().positive().nullable(),
  }),
});
const reminder = z.object({ content: text.trim().min(1), recurrence: recurrence.nullable() });
const ticket = z.object({ title: text.trim().min(1), description: text });
export interface ProposedReminder {
  content: string;
  recurrence: RecurrenceSpec | null;
}
export type ProposedTicket = z.infer<typeof ticket>;
const sourceUrl = text.url().refine(value => {
  if (!URL.canParse(value)) return false;
  const url = new URL(value);
  return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password;
});
const research = z.object({
  kind: z.literal('research'),
  query: text.min(1),
  provider: z.enum(['brave', 'perplexity', 'wikipedia']),
  summary: text.nullable(),
  sources: z.array(z.object({ title: text.min(1), url: sourceUrl, excerpt: text })),
});
export type ResearchProposal = z.infer<typeof research>;
export const selectionAnswerSchema = z.object({
  proposal: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('text'), text: text.min(1) }),
    research,
    z.object({ kind: z.literal('task'), task }),
    z.object({ kind: z.literal('event'), event }),
    z.object({ kind: z.literal('memory'), memory }),
    z.object({ kind: z.literal('reminder'), reminder }),
    z.object({ kind: z.literal('ticket'), ticket }),
  ]),
  usage: usage.nullable(),
});
export type SelectionAnswer = z.infer<typeof selectionAnswerSchema>;
export type CreationProposal = Extract<SelectionAnswer['proposal'], { kind: Destination }>;
export function isDestination(action: SelectionAction): action is Destination {
  return (
    action === 'task' ||
    action === 'event' ||
    action === 'memory' ||
    action === 'reminder' ||
    action === 'ticket'
  );
}
