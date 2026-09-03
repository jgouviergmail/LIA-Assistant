/**
 * What a batch left untouched, as one sentence (ADR-259).
 *
 * Every batch (documents moved or deleted, templates added or deleted)
 * answers with the ids it handled and the ones it skipped, each with a
 * stable code. This turns the skipped part into a localized sentence naming
 * the count and every distinct reason once, under the caller's key prefix:
 * `<prefix>.skipped` for the sentence, `<prefix>.skip.<code>` for a reason.
 */

export type Translate = (key: string, options?: Record<string, unknown>) => string;

export function skippedSentence(
  t: Translate,
  prefix: string,
  skipped: readonly { code: string }[]
): string {
  const reasons = [...new Set(skipped.map(item => item.code))]
    .map(code => t(`${prefix}.skip.${code}`, { defaultValue: code }))
    .join(', ');
  return t(`${prefix}.skipped`, { count: skipped.length, reasons });
}
