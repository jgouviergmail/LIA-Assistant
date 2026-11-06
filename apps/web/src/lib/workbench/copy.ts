/**
 * Copies a text (ADR-369, lot 2).
 *
 * A page without a clipboard (an insecure origin) has no `navigator.clipboard`: the
 * call throws there, and an `async` turns that into the refusal its caller says.
 *
 * @param text - What to copy.
 */
export async function copyText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}
