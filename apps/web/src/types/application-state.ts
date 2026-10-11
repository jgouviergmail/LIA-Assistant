import { z } from '@/lib/zod';

const applicationResource = z.enum([
  'meetings',
  'meeting_templates',
  'meeting_preferences',
  'skills',
  'plugins',
  'user_mcp',
  'profile',
  'briefing_preferences',
  'chat_shortcuts',
  'locations',
  'heartbeat',
  'channels',
  'connector_preferences',
  'shared_mcp_preferences',
  'connectors',
  'avatar',
  'live_connectors',
  'notification_devices',
  'live_preferences',
  'phone_identity',
  'device_sessions',
  'account_export',
  'routines',
  'reminders',
  'memories',
  'interests',
  'open_loops',
  'habits',
  'psyche',
  'journals',
  'health_metrics',
  'relations',
  'peers',
  'workboard',
  'spaces',
  'generated_assets',
]);

/** Hints contain identities and field names only; values come from authenticated queries. */
export const applicationStateChangeSchema = z
  .object({
    schema_version: z.literal(1),
    command_id: z.string().uuid(),
    actor_id: z.string().uuid(),
    resources: z.array(applicationResource).min(1).max(applicationResource.options.length),
    changed_fields: z
      .array(
        z
          .string()
          .max(64)
          .regex(/^[a-z_]+$/)
      )
      .min(1)
      .max(64),
    observed_at: z.string().datetime({ offset: true }),
  })
  .strict();

export type ApplicationStateChange = z.infer<typeof applicationStateChangeSchema>;
