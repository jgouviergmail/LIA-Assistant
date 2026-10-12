import { z } from '@/lib/zod';

const skill = z
  .object({
    name: z.string(),
    description: z.string(),
    descriptions: z.record(z.string(), z.string()).nullable(),
    scope: z.enum(['admin', 'user']),
    category: z.string().nullable(),
    priority: z.number().int(),
    always_loaded: z.boolean(),
    has_scripts: z.boolean(),
    has_plan_template: z.boolean(),
    enabled_for_user: z.boolean(),
    admin_enabled: z.boolean(),
    dialogue: z.boolean(),
    outputs: z.array(z.string()).nullable(),
    skill_id: z.string().uuid(),
    provenance: z.enum(['system', 'authored', 'url', 'plugin', 'library']).nullable(),
  })
  .strict();

/** Exact public browser selection; private archive witnesses are never accepted here. */
export const skillFileUploadSelectionSchema = z
  .object({
    request: z.object({ replace_skill_id: z.string().uuid().nullable() }).strict(),
    previous: skill.nullable(),
    max_file_size_bytes: z.number().int().positive(),
    max_package_files: z.number().int().positive(),
    max_decompressed_bytes: z.number().int().positive(),
    max_personal_skills: z.number().int().positive(),
    allowed_extensions: z.tuple([z.literal('.md'), z.literal('.zip')]),
    browser_file_confirmation_required: z.literal(true),
  })
  .strict()
  .refine(value => value.request.replace_skill_id === (value.previous?.skill_id ?? null));

export type SkillFileUploadSelection = z.infer<typeof skillFileUploadSelectionSchema>;

export const skillFileUploadReceiptSchema = z
  .object({
    skill_file_upload: z
      .object({ skill_id: z.string().uuid(), name: z.string(), provenance: z.literal('authored') })
      .strict(),
    upload_accepted: z.literal(true),
    cache_refresh_pending: z.boolean(),
  })
  .strict();

export const skillFileUploadResultSchema = z
  .object({
    success: z.literal(true),
    phase: z.literal('committed'),
    committed: z.literal(true),
    no_op: z.literal(false),
    error_code: z.null(),
    interaction: z.null(),
    values: skillFileUploadReceiptSchema,
  })
  .strict();
