/**
 * The refusals the « Tools » section's API names (`detail.code`), as the sentence
 * to show (ADR-369).
 *
 * Every code the API sends has a plain sentence in the six languages (a backend
 * test pins the list below to `WORKBENCH_CODES` and every key to the locales).
 * A figure the API sends beside a code — a wait, a size bound, a recipient's
 * position, a provider's limit, what became of a first submission — chooses a
 * richer sentence that quotes it; a figure it did not send, or sent unreadable,
 * leaves the plain one: a sentence quoting what nobody sent would be a claim
 * nobody made. Our own per-account window answers a 429 naming no code of
 * ours: it is told like a provider's throttle, with the wait it names.
 */
import { getApiErrorFields, getApiErrorStatus } from '@/lib/api-error';

/** Every code the workbench API refuses with — `domains/workbench/errors.py`. */
export const WORKBENCH_ERROR_CODES = [
  'not_connected',
  'reconnect_required',
  'provider_rate_limited',
  'provider_unavailable',
  'item_gone',
  'stale_handle',
  'card_source_changed',
  'conflict',
  'name_taken',
  'name_refused',
  'folder_not_empty',
  'too_large',
  'invalid_recipient',
  'already_submitted',
  'outcome_unknown',
  'not_supported_by_provider',
  'provider_refused',
  'invalid_request',
  'event_left_behind',
  'task_left_behind',
  'event_start_outside_series',
  'not_a_contacts_file',
  'not_an_image',
  'too_many_cards',
  'file_locked',
  'assist_empty',
  'assist_unreadable',
  'assist_not_found',
  'assist_quota',
  'assist_paused',
  'assist_failed',
] as const;

export type WorkbenchErrorCode = (typeof WORKBENCH_ERROR_CODES)[number];

/** A refusal, as the sentence the reader is shown. */
export interface WorkbenchRefusal {
  /** The i18n key of its sentence. */
  key: string;
  /** The figures it quotes, as the API sent them (converted to the reader's unit). */
  values?: Record<string, number>;
}

/** What a replay may be told of the first submission (`SubmissionOutcome`). */
const SUBMISSION_OUTCOMES: ReadonlySet<string> = new Set(['done', 'pending', 'unknown']);

const CODES: ReadonlySet<string> = new Set(WORKBENCH_ERROR_CODES);

const BYTES_PER_MEGABYTE = 1024 * 1024;

function isCode(value: string): value is WorkbenchErrorCode {
  return CODES.has(value);
}

/** A count the API sent: a whole number, never negative. */
function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
}

type RefusalFacts = Readonly<Record<string, unknown>>;
type Enrichment = (prefix: string, facts: RefusalFacts) => WorkbenchRefusal | null;

const waitFor: Enrichment = (prefix, facts) => {
  const seconds = count(facts.retry_after);
  return seconds && seconds > 0 ? { key: `${prefix}_wait`, values: { seconds } } : null;
};

/** The richer sentence each code's facts allow; a code absent here has its plain one. */
const ENRICHMENTS: Readonly<Partial<Record<WorkbenchErrorCode, Enrichment>>> = {
  provider_rate_limited: waitFor,
  provider_unavailable: waitFor,
  too_large: (prefix, facts) => {
    const bytes = count(facts.max_bytes);
    if (!bytes) return null;
    return {
      key: `${prefix}_bounded`,
      values: { megabytes: Number((bytes / BYTES_PER_MEGABYTE).toFixed(1)) },
    };
  },
  invalid_recipient: (prefix, facts) => {
    const index = count(facts.index);
    return index === null ? null : { key: `${prefix}_at`, values: { position: index + 1 } };
  },
  already_submitted: (prefix, facts) => {
    const outcome = facts.outcome;
    return typeof outcome === 'string' && SUBMISSION_OUTCOMES.has(outcome)
      ? { key: `${prefix}_${outcome}` }
      : null;
  },
  too_many_cards: (prefix, facts) => {
    const items = count(facts.max_items);
    return items ? { key: `${prefix}_bounded`, values: { count: items } } : null;
  },
  not_supported_by_provider: (prefix, facts) => {
    const bound = count(facts.bound);
    return bound ? { key: `${prefix}_bounded`, values: { bound } } : null;
  },
};

/** The richer sentence a code's facts allow, or null for its plain one. */
function enriched(code: WorkbenchErrorCode, facts: RefusalFacts): WorkbenchRefusal | null {
  return ENRICHMENTS[code]?.(`workbench.errors.${code}`, facts) ?? null;
}

/**
 * The sentence of a refusal the workbench API named.
 *
 * @param error - Anything a `catch` block received.
 * @returns The refusal's sentence, or null when the API named none of ours
 *   (the caller then says its own generic sentence).
 */
export function workbenchRefusal(error: unknown): WorkbenchRefusal | null {
  const fields = getApiErrorFields(error);
  const code = fields?.code;
  if (!fields || typeof code !== 'string' || !isCode(code)) return ownWindow(error);
  return enriched(code, fields) ?? { key: `workbench.errors.${code}` };
}

/**
 * The sentence of a refusal code the API reported beside an answer (one
 * calendar of a window that could not be read).
 *
 * @param code - A `detail.code`, as the API sent it.
 * @returns Its sentence, or null for a code that is none of ours.
 */
export function refusalOfCode(code: string): WorkbenchRefusal | null {
  return isCode(code) ? { key: `workbench.errors.${code}` } : null;
}

/** The `detail` object of a rejected call, whatever it names. */
function detailOf(error: unknown): Readonly<Record<string, unknown>> | undefined {
  const data = typeof error === 'object' && error !== null ? Reflect.get(error, 'data') : null;
  const detail = typeof data === 'object' && data !== null ? Reflect.get(data, 'detail') : null;
  return typeof detail === 'object' && detail !== null ? { ...detail } : undefined;
}

/** Our own window (`create_user_rate_limiter`): a 429 that names no code of ours. */
function ownWindow(error: unknown): WorkbenchRefusal | null {
  if (getApiErrorStatus(error) !== 429) return null;
  const seconds = count(detailOf(error)?.retry_after_seconds);
  return seconds && seconds > 0
    ? { key: 'workbench.errors.provider_rate_limited_wait', values: { seconds } }
    : { key: 'workbench.errors.provider_rate_limited' };
}
