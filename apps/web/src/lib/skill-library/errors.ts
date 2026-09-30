/**
 * The refusals the skill library's API names (`detail.code`), as the sentence to show (ADR-327).
 *
 * Every code the API sends has a sentence in the six languages (a backend
 * guard pins the pair, `test_errors.py`). A fact the API published beside its
 * code — the audit's risk, when GitHub's allowance returns, the largest skill
 * accepted, the new name of a renamed skill — travels into the sentence; a
 * refusal whose facts are missing says its plain sentence, never a figure
 * nobody sent.
 */
import { getApiErrorFields } from '@/lib/api-error';

import type { LibraryRisk } from './types';

/** A refusal, as the sentence the reader is shown. */
export interface LibraryRefusal {
  /** The i18n key of its sentence. */
  key: string;
  /** Its interpolation values. */
  values?: Record<string, string | number>;
  /** The risk an audit gave, for a sentence that names it in the reader's words. */
  risk?: LibraryRisk;
}

const PREFIX = 'settings.skills.library.errors';

/** Told in their own words, with nothing beside the code. */
const PLAIN: ReadonlySet<string> = new Set([
  'skill_library_source_invalid',
  'skill_library_origin_unsupported',
  'skill_library_not_found',
  'skill_library_ambiguous',
  'skill_library_unreachable',
  'skill_library_name_taken',
  'skill_library_already_installed',
  'skill_library_not_installed',
  'skill_library_quota_reached',
  'skill_library_invalid_skill',
]);

const RISKS: ReadonlySet<string> = new Set(['safe', 'low', 'medium', 'high', 'critical']);

/** A clock time the reader recognises, in their own locale. */
function clockOf(epochSeconds: number, lng: string): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString(lng, {
    hour: '2-digit',
    minute: '2-digit',
  });
}

type Fields = Readonly<Record<string, unknown>>;

/** The refusals whose sentence quotes a fact, keyed by code. */
const QUOTING: Readonly<Record<string, (fields: Fields, lng: string) => LibraryRefusal>> = {
  skill_library_query_invalid: fields =>
    typeof fields.min_chars === 'number' && typeof fields.max_chars === 'number'
      ? {
          key: `${PREFIX}.skill_library_query_invalid`,
          values: { min: fields.min_chars, max: fields.max_chars },
        }
      : { key: `${PREFIX}.skill_library_query_invalid_plain` },
  skill_library_rate_limited: (fields, lng) =>
    typeof fields.reset_at === 'number'
      ? {
          key: `${PREFIX}.skill_library_rate_limited`,
          values: { time: clockOf(fields.reset_at, lng) },
        }
      : { key: `${PREFIX}.skill_library_rate_limited_plain` },
  skill_library_too_large: fields => {
    if (typeof fields.max_files === 'number') {
      return { key: `${PREFIX}.skill_library_too_large_files`, values: { max: fields.max_files } };
    }
    if (typeof fields.max_kb === 'number') {
      return { key: `${PREFIX}.skill_library_too_large_kb`, values: { max: fields.max_kb } };
    }
    return { key: `${PREFIX}.skill_library_too_large` };
  },
  skill_library_audit_blocked: fields =>
    typeof fields.risk === 'string' && RISKS.has(fields.risk)
      ? { key: `${PREFIX}.skill_library_audit_blocked`, risk: fields.risk as LibraryRisk }
      : { key: `${PREFIX}.skill_library_audit_blocked_plain` },
  skill_library_renamed: fields =>
    typeof fields.name === 'string'
      ? { key: `${PREFIX}.skill_library_renamed`, values: { name: fields.name } }
      : { key: `${PREFIX}.skill_library_renamed_plain` },
};

/**
 * The sentence of a refusal the library's API named.
 *
 * @param error - Anything a `catch` block received.
 * @param lng - The reader's language (a clock time is written in it).
 * @returns The refusal, or `null` when the API named none (the caller says
 *   its own generic sentence).
 */
export function libraryRefusalOf(error: unknown, lng: string): LibraryRefusal | null {
  const fields = getApiErrorFields(error);
  const code = fields?.code;
  if (!fields || typeof code !== 'string') return null;
  if (PLAIN.has(code)) return { key: `${PREFIX}.${code}` };
  const quote = QUOTING[code];
  return quote ? quote(fields, lng) : null;
}

/** Every sentence key a refusal can be told with — what the locales must hold. */
export const LIBRARY_REFUSAL_KEYS: readonly string[] = [
  ...[...PLAIN].map(code => `${PREFIX}.${code}`),
  ...[
    'skill_library_query_invalid',
    'skill_library_query_invalid_plain',
    'skill_library_rate_limited',
    'skill_library_rate_limited_plain',
    'skill_library_too_large',
    'skill_library_too_large_files',
    'skill_library_too_large_kb',
    'skill_library_audit_blocked',
    'skill_library_audit_blocked_plain',
    'skill_library_renamed',
    'skill_library_renamed_plain',
  ].map(key => `${PREFIX}.${key}`),
];
