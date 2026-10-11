import { z } from '@/lib/zod';

const phase = z.enum(['pending', 'claimed', 'resuming', 'committed', 'waiting', 'failed', 'conflict', 'cancelled', 'expired']);
const timestamp = z.string().datetime({ offset: true });
const interaction = z.object({
  interaction_id: z.string().uuid(), kind: z.enum(['secure', 'device']), expires_at: timestamp,
}).strict();
const outcome = z.object({
  success: z.boolean(), phase, committed: z.boolean(), no_op: z.boolean(),
  values: z.record(z.string(), z.json()), error_code: z.string().nullable(),
  interaction: interaction.nullable(),
}).strict();

/** Current observation is data; it cannot grant permission to execute an action. */
const statusShape = z.object({
  schema_version: z.literal(1), command_id: z.string().uuid(),
  operation_id: z.string().min(1).max(100), phase, expires_at: timestamp,
  interaction: interaction.nullable(), outcome: outcome.nullable(),
  prior_outcome: outcome.nullable().optional(),
}).strict();

type CommandStatusShape = z.infer<typeof statusShape>;

function coherentInteraction(value: CommandStatusShape): boolean {
  const pending = value.interaction;
  return (value.phase === 'waiting') === (pending !== null)
    && (!pending || (pending.interaction_id === value.command_id && pending.expires_at === value.expires_at));
}

function coherentReceipt(value: CommandStatusShape): boolean {
  const receipt = value.outcome;
  const pending = value.interaction;
  if (receipt === null) return ['pending', 'claimed', 'resuming', 'cancelled', 'expired'].includes(value.phase);
  if (['pending', 'claimed', 'resuming'].includes(receipt.phase)) return false;
  return receipt.phase === value.phase
    && receipt.success === (receipt.phase === 'committed' && receipt.committed)
    && JSON.stringify(receipt.interaction) === JSON.stringify(pending)
    && (!pending || (receipt.error_code === null && !receipt.no_op && (pending.kind !== 'secure' || !receipt.committed)));
}

function coherentPriorReceipt(value: CommandStatusShape): boolean {
  const prior = value.prior_outcome;
  if (value.phase !== 'resuming') return !prior;
  if (!prior || prior.phase !== 'waiting' || !prior.interaction) return false;
  return coherentInteraction({ ...value, phase: 'waiting', interaction: prior.interaction })
    && coherentReceipt({ ...value, phase: 'waiting', interaction: prior.interaction, outcome: prior })
    && value.outcome === null && value.interaction === null;
}

export const applicationCommandStatusSchema = statusShape.superRefine((value, context) => {
  if (!coherentInteraction(value) || !coherentReceipt(value) || !coherentPriorReceipt(value)) {
    context.addIssue({ code: 'custom', message: 'Incoherent command status' });
  }
});

export type ApplicationCommandStatus = z.infer<typeof applicationCommandStatusSchema>;
