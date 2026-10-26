/** Keep complete graphemes within the actual cached actor surface. */
const graphemes = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
export function fitActorLabel(
  value: string,
  measure: (text: string) => number,
  width: number
): string {
  if (measure(value) <= width) return value;
  if (measure('…') > width) return '';
  let result = '';
  for (const { segment } of graphemes.segment(value)) {
    if (measure(result + segment + '…') > width) break;
    result += segment;
  }
  return result + '…';
}
