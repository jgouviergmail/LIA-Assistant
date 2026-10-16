/**
 * How the voice library words what the API says (ADR-345): a slot's name, a
 * list joined the reader's way, and the sentence a refusal deserves.
 *
 * The API names each refusal by a stable code and the facts its sentence
 * quotes (a bound, the slots speaking with a voice); the sentence lives HERE,
 * in six languages, and a backend guard holds every code it can send to a key
 * of `settings.admin.voiceLibrary.errors`. The instance's daily pause is the
 * usage limits' own shape (`detail.error_code`), read beside it.
 */

import { getApiErrorFields } from '@/lib/api-error';
import type { Translate } from '@/lib/batch-report';
import { formatFileSize } from '@/lib/utils/image-compress';

const PREFIX = 'settings.admin.voiceLibrary.errors';

/** The instance's daily pause, as the usage limits name it. */
const INSTANCE_PAUSE = 'instance_budget_exhausted';

/** A slot's name as the library shows it; an unknown slot keeps its id. */
export function slotName(slot: string, t: Translate): string {
  return t(`settings.admin.voiceLibrary.slots.${slot}`, { defaultValue: slot });
}

/** Items joined the reader's way (« A et B », « A和B »), plain commas if unsupported. */
export function joinedList(items: readonly string[], locale: string): string {
  try {
    return new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(items);
  } catch {
    return items.join(', ');
  }
}

/** The slots' names, joined the reader's way. */
export function slotsSentence(slots: readonly string[], t: Translate, locale: string): string {
  return joinedList(
    slots.map(slot => slotName(slot, t)),
    locale
  );
}

function instancePaused(error: unknown): boolean {
  const data = (error as { data?: { detail?: unknown } } | null)?.data;
  const detail = data?.detail;
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as { error_code?: unknown }).error_code === INSTANCE_PAUSE
  );
}

function asNumber(value: unknown): number {
  return typeof value === 'number' ? value : 0;
}

function asList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

/**
 * Translate a rejected library request.
 *
 * @param error - What the request rejected with.
 * @param t - The section's translator.
 * @param locale - The Intl locale a list of slots is joined in.
 * @returns The refusal's sentence, or the section's generic one.
 */
export function libraryRefusal(error: unknown, t: Translate, locale: string): string {
  if (instancePaused(error)) return t(`${PREFIX}.${INSTANCE_PAUSE}`);
  const fields = getApiErrorFields(error);
  const code = fields?.code;
  if (typeof code !== 'string') return t(`${PREFIX}.generic`);
  return t(`${PREFIX}.${code}`, {
    defaultValue: t(`${PREFIX}.generic`),
    max: asNumber(
      fields?.max_samples ?? fields?.max_chars ?? fields?.max_seconds ?? fields?.max_pins
    ),
    perFile: formatFileSize(asNumber(fields?.max_bytes)),
    total: formatFileSize(asNumber(fields?.total_max_bytes)),
    formats: asList(fields?.formats).join(', '),
    slots: slotsSentence(asList(fields?.slots), t, locale),
  });
}
