/**
 * Presentation-only splitter for long grouped FAQ answers.
 *
 * The "What can I ask LIA?" answer is authored in the locale files as one flat
 * HTML string: an intro line, then domain blocks shaped as
 * `<br><br><strong>HEADING</strong><br>` followed by `• "…"` bullet lines
 * separated by single `<br>`s. Rendering ~10k chars of that as-is produces an
 * unreadable wall of text, so the public FAQ splits it into per-domain
 * collapsible groups — WITHOUT touching the source strings (the translation
 * files stay byte-identical; `__tests__/faq-answer-groups.test.ts` proves the
 * split preserves every word across all locales and falls back otherwise).
 */

export interface AnswerGroup {
  /** Inner HTML of the `<strong>` heading (usually an emoji + label). */
  heading: string;
  /** Bullet lines with the leading `• ` marker stripped (inline HTML kept). */
  items: string[];
}

export interface GroupedAnswer {
  /** HTML before the first heading (the intro sentence). */
  intro: string;
  groups: AnswerGroup[];
}

/** Delimiter the locale files use between domain blocks. */
const GROUP_DELIMITER = /<br\s*\/?>\s*<br\s*\/?>\s*<strong>(.*?)<\/strong>\s*<br\s*\/?>/g;

/**
 * Grouping only kicks in when the answer clearly follows the grouped shape;
 * below this many headings the answer renders untouched. Guards against
 * accidentally restructuring answers that merely contain a bold run (e.g. the
 * zh q4, which is a different, short answer).
 */
const MIN_GROUPS = 3;

/**
 * Split a grouped FAQ answer into intro + per-heading bullet groups.
 *
 * Args:
 *   html: The raw answer HTML from the translation file.
 *
 * Returns:
 *   The grouped structure, or null when the answer does not follow the
 *   grouped shape (callers must then render the answer as-is).
 */
export function splitAnswerGroups(html: string): GroupedAnswer | null {
  const parts = html.split(GROUP_DELIMITER);
  // split() with one capture group yields [intro, heading1, body1, heading2, …]
  if (parts.length < 1 + 2 * MIN_GROUPS) return null;

  const intro = parts[0].trim();
  const groups: AnswerGroup[] = [];

  for (let i = 1; i < parts.length; i += 2) {
    const heading = parts[i].trim();
    const body = parts[i + 1] ?? '';
    const items = body
      .split(/<br\s*\/?>/)
      .map(line => line.replace(/^\s*•\s*/, '').trim())
      .filter(line => line.length > 0);
    if (heading.length === 0 || items.length === 0) return null;
    groups.push({ heading, items });
  }

  return { intro, groups };
}
