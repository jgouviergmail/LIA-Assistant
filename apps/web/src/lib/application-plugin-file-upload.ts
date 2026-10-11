import { z } from '@/lib/zod';
import type {
  InstalledPlugin,
  PluginImportReport,
  PluginIssue,
  PluginComponentReport,
} from '@/hooks/usePlugins';

const plugin = z
  .object({
    id: z.string().uuid(),
    name: z.string(),
    version: z.string().nullable(),
    description: z.string().nullable(),
    spec_version: z.string(),
    skill_names: z.array(z.string()),
    server_names: z.array(z.string()),
    created_at: z.string().datetime({ offset: true }).nullable(),
    updated_at: z.string().datetime({ offset: true }).nullable(),
  } satisfies Record<keyof InstalledPlugin, z.ZodType>)
  .strict();

export const pluginFileUploadSelectionSchema = z
  .object({
    request: z.object({ replace_plugin_id: z.string().uuid().nullable() }).strict(),
    previous: plugin.nullable(),
    max_file_size_bytes: z.number().int().positive(),
    max_package_files: z.number().int().positive(),
    max_decompressed_bytes: z.number().int().positive(),
    max_personal_plugins: z.number().int().positive(),
    allowed_extensions: z.tuple([z.literal('.zip')]),
    browser_file_confirmation_required: z.literal(true),
  })
  .strict()
  .refine(value => value.request.replace_plugin_id === (value.previous?.id ?? null));
export type PluginFileUploadSelection = z.infer<typeof pluginFileUploadSelectionSchema>;

const issue = z
  .object({
    code: z.enum([
      'manifest_not_an_object',
      'manifest_schema_unsupported',
      'manifest_name_invalid',
      'manifest_field_invalid',
      'manifest_unknown_field',
      'manifest_extensions_not_object',
      'mcp_config_invalid',
      'mcp_schema_unsupported',
      'server_entry_invalid',
      'server_transport_unsupported',
      'server_url_policy_https',
      'component_location_invalid',
      'skill_invalid',
      'skill_name_conflict',
      'server_name_conflict',
      'server_create_failed',
    ]),
    field: z.string().nullable(),
    detail: z.string().nullable(),
  } satisfies Record<keyof PluginIssue, z.ZodType>)
  .strict();
const report = z
  .object({
    plugin_id: z.string().uuid(),
    name: z.string(),
    version: z.string().nullable(),
    description: z.string().nullable(),
    updated: z.boolean(),
    file_cleanup_pending: z.boolean(),
    components: z.array(
      z
        .object({
          kind: z.enum(['skill', 'mcp_server']),
          key: z.string(),
          status: z.enum(['installed', 'updated', 'skipped', 'removed']),
          issues: z.array(issue),
        } satisfies Record<keyof PluginComponentReport, z.ZodType>)
        .strict()
    ),
    warnings: z.array(issue),
  } satisfies Record<keyof PluginImportReport, z.ZodType>)
  .strict();
export const pluginFileUploadReceiptSchema = z
  .object({
    plugin_file_upload: report,
    upload_accepted: z.literal(true),
    file_cleanup_pending: z.boolean(),
    cache_refresh_pending: z.boolean(),
  })
  .strict();
export const pluginFileUploadResultSchema = z
  .object({
    success: z.literal(true),
    phase: z.literal('committed'),
    committed: z.literal(true),
    no_op: z.literal(false),
    error_code: z.null(),
    interaction: z.null(),
    values: pluginFileUploadReceiptSchema,
  })
  .strict();
