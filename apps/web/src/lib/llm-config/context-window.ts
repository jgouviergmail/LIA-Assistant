/**
 * The context window an operator types, and the tokens LIA stores (ADR-278).
 *
 * `OLLAMA_NUM_CTX` was one instance-wide number handed to every Ollama tag
 * whatever its size — a production deployment set 128 000 and a 4 B model was
 * asked to allocate the same window as a 27 B one. The number moved onto the
 * configured SLOT, beside the model it applies to.
 *
 * An operator thinks « 32 k », not « 32 768 »: the field takes and shows k, and
 * these two functions are the only place the two units meet. They are pure, so
 * the conversion is testable without a dialog.
 */

/** One k, as an operator means it — a binary k, like every context window. */
export const TOKENS_PER_K = 1024;

/**
 * Tokens as the k figure a field shows.
 *
 * @param tokens - A window in tokens.
 * @returns The same window in k, at most one decimal so 32 768 reads `32` and
 *   an odd 100 000 still reads something exact enough to retype.
 */
export function toK(tokens: number): number {
  return Math.round((tokens / TOKENS_PER_K) * 10) / 10;
}

/**
 * A typed k figure back to tokens.
 *
 * Accepts a comma as the decimal mark: the admin surface is read in six
 * languages and four of them write `32,5`.
 *
 * @param raw - What the operator typed.
 * @returns The window in tokens, or null for an empty, zero, negative or
 *   unusable entry — which is how the field says « use the model's own ».
 */
export function fromK(raw: string): number | null {
  const value = Number.parseFloat(raw.replace(',', '.'));
  if (!Number.isFinite(value) || value <= 0) return null;
  return Math.round(value * TOKENS_PER_K);
}
