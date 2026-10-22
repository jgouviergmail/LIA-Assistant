import { z } from '@/lib/zod';

export const discussionSourceSchema = z.enum([
  'calendar',
  'emails',
  'contacts',
  'tasks',
  'weather',
  'location',
  'memories',
  'journals',
  'portrait',
  'open_loops',
  'habits',
  'relations',
  'health',
  'conversations',
  'meetings',
  'peers',
  'peer_messages',
  'interests',
  'reminders',
  'scheduled_actions',
  'workboard',
  'sms',
]);
export const discussionTopics = [
  'health',
  'relationships',
  'finances',
  'grief',
  'intimacy',
] as const;
export const discussionFeedbackSchema = z.enum(['useful', 'not_now', 'avoid_topic', 'incorrect']);
export const discussionOpeningSchema = z.object({
  id: z.string().uuid(),
  message_id: z.string().uuid(),
  created_at: z.string().datetime({ offset: true }),
  content: z.string(),
  state: z.enum(['pending', 'engaged', 'dismissed', 'expired']),
  feedback: discussionFeedbackSchema.nullable(),
  reason: z.string().nullable().optional(),
  evidence: z
    .array(
      z.object({
        source: discussionSourceSchema,
        observed_at: z.string(),
        occurred_at: z.string().nullable(),
        assertion: z.string(),
      })
    )
    .default([]),
});
export const discussionOpeningPageSchema = z.object({
  items: z.array(discussionOpeningSchema),
  total: z.number().int().nonnegative(),
  next_cursor: z.string().uuid().nullable(),
});
export type DiscussionFeedback = z.infer<typeof discussionFeedbackSchema>;
export type DiscussionOpeningPage = z.infer<typeof discussionOpeningPageSchema>;
export const discussionPurgePreviewSchema = z.object({
  context_epoch: z.number().int().nonnegative(),
  generation: z.number().int().nonnegative(),
  selected_count: z.number().int().nonnegative(),
  affected_count: z.number().int().nonnegative(),
});
export interface DiscussionContextFence {
  expected_epoch: number;
  expected_generation: number;
}
const topic = z.enum(discussionTopics);
const policy = z.object({
  enabled: z.boolean(),
  start_hour: z.number().int().min(0).max(23),
  end_hour: z.number().int().min(0).max(23),
  timezone: z.string(),
  daily_max: z.number().int().positive().nullable(),
  sources: z.array(discussionSourceSchema),
  sensitive_topics: z.array(topic),
  forbidden_topics: z.array(z.string().min(1).max(160)).default([]),
  paused_until: z.string().nullable(),
  revision: z.number().int().nonnegative(),
});
export const discussionSettingsSchema = z.object({
  policy,
  sources: z.array(
    z.object({
      key: discussionSourceSchema,
      operations: z.array(z.string()),
      indivisible: z.boolean(),
      dependencies: z.array(discussionSourceSchema).default([]),
    })
  ),
  producer_enabled: z.boolean(),
  budget_configured: z.boolean(),
  pause_hours: z.number().int().positive(),
});
export const discussionContextItemSchema = z.object({
  id: z.string().uuid(),
  kind: z.enum(['observation', 'episode', 'pattern']),
  summary: z.string(),
  qualification: z.enum([
    'planned',
    'reported',
    'observed',
    'declared',
    'possible',
    'contradicted',
    'unknown',
  ]),
  revision: z.number().int().positive(),
  excluded: z.boolean().default(false),
  explicitly_excluded: z.boolean().default(false),
  generation: z.number().int().positive(),
  proofs: z
    .array(
      z.object({
        root: z.string(),
        reference: z.string(),
        source: discussionSourceSchema,
        source_account: z.string(),
        version: z.string(),
        support_roots: z.array(z.string()),
        required_sources: z.array(discussionSourceSchema),
        sensitive_topics: z.array(topic),
        observed_at: z.string(),
        occurred_at: z.string().nullable(),
        expires_at: z.string(),
      })
    )
    .min(1),
});
export const discussionContextSchema = z.object({
  generation: z.number().int().nonnegative(),
  context_epoch: z.number().int().nonnegative(),
  forgotten_at: z.string().nullable(),
  refresh_requested: z.boolean(),
  items: z.array(discussionContextItemSchema),
  total: z.number().int().nonnegative(),
  next_cursor: z.string().uuid().nullable(),
  exclusions_total: z.number().int().nonnegative().default(0),
  exclusions_next_cursor: z.string().uuid().nullable().default(null),
  exclusions: z.array(z.object({ item_id: z.string().uuid(), roots: z.array(z.string()) })),
  coverage: z.array(
    z.object({
      source: discussionSourceSchema,
      status: z.string(),
      complete: z.boolean(),
      kind: z.string(),
    })
  ),
});
export type DiscussionSettings = z.infer<typeof discussionSettingsSchema>;
export type DiscussionPolicy = DiscussionSettings['policy'];
export type DiscussionContext = z.infer<typeof discussionContextSchema>;
export type DiscussionContextItem = z.infer<typeof discussionContextItemSchema>;
export type DiscussionPolicyPatch = Partial<Omit<DiscussionPolicy, 'timezone' | 'revision'>>;

const count = z.number().int().nonnegative();
const euros = z.number().nonnegative();
const instant = z.string().datetime({ offset: true });
/** What one run cost, from its own ledger row: the chat meter's figures. */
export const discussionRunUsageSchema = z.object({
  tokens_in: count,
  tokens_out: count,
  tokens_cache: count,
  google_requests: count,
  cost_eur: euros,
});
/** What a run read and interpreted: counts only, never content. */
export const discussionRunStatsSchema = z.object({
  pages: z.record(z.string(), count),
  facts_read: count,
  facts_admitted: count,
  facts_offered: count,
  facts_unclassified: count,
  context_calls: count,
  proposals: count,
  proposals_refused: count,
  research_refused: count,
  context_updates: count,
  items: count,
});
/** One producer run: a rebuild the person asked for, or an automatic opening run. */
export const discussionRunSchema = z.object({
  kind: z.enum(['rebuild', 'opening']),
  state: z.enum(['claimed', 'completed', 'skipped', 'failed', 'abandoned']),
  claimed_at: instant,
  settled_at: instant.nullable(),
  // The server's closed vocabulary (RunReason): every member has its sentence,
  // held by a backend guard over the locale files.
  reason: z.string().min(1).nullable(),
  stats: discussionRunStatsSchema.nullable(),
  usage: discussionRunUsageSchema.nullable(),
});
/** The ceilings that can stop a run, in the order a run meets them; never amounts. */
export const discussionCeilingSchema = z.enum([
  'instance_budget',
  'usage_limit',
  'run_ceiling',
  'owner_day',
  'instance_day',
]);
export const discussionActivitySchema = z.object({
  rebuild: z.enum(['idle', 'requested', 'running']),
  obstacle: z.enum(['controls_over_budget', 'ceiling_reached']).nullable(),
  last_rebuild: discussionRunSchema.nullable(),
  // The latest settled run whose build updated the context, whatever its kind.
  last_update: discussionRunSchema.nullable(),
  // The latest settled run: the figures the page shows are this run's own.
  last_run: discussionRunSchema.nullable(),
  budget: z.object({
    configured: z.boolean(),
    reached: discussionCeilingSchema.nullable(),
    resets_at: instant.nullable(),
  }),
});
export type DiscussionActivity = z.infer<typeof discussionActivitySchema>;
