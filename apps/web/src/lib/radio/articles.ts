/**
 * The articles a session cited (ADR-324), computed apart from the components.
 *
 * The page lists every story the programme has told so far, each once, in the
 * order it first aired: a panel the listener opened stays where it is while
 * the programme moves on, and a list reordered under a reader would move the
 * text they are reading. Only a source that IS a story (`article_id`) is
 * offered — the listener's own records have no article to open.
 */
import type { RadioSegment } from './types';

/** A story the page can open (`GET /radio/articles/{id}`). */
export interface RadioArticleRef {
  /** The story, as the transcript source names it (`article_id`). */
  id: string;
  /** Its outlet, as the transcript shows it. */
  outlet: string;
  /** The article at its outlet, as the feed gave it — reachable without opening (translating) it. */
  url: string | null;
  publishedAt: string | null;
}

/**
 * The articles heard so far, plus those a segment going on air cites.
 *
 * @returns The same list when the segment cites nothing new, so a view that
 *   did not change keeps its identity.
 */
export function withArticles(
  heard: readonly RadioArticleRef[],
  segment: RadioSegment
): readonly RadioArticleRef[] {
  const known = new Set(heard.map(article => article.id));
  const added: RadioArticleRef[] = [];
  for (const line of segment.transcript) {
    for (const source of line.sources) {
      if (source.article_id === null || known.has(source.article_id)) continue;
      known.add(source.article_id);
      added.push({
        id: source.article_id,
        outlet: source.label,
        url: source.url,
        publishedAt: source.published_at,
      });
    }
  }
  return added.length === 0 ? heard : [...heard, ...added];
}

/** An article's paragraphs: its text cut at the blank lines, nothing empty kept. */
export function paragraphs(text: string): string[] {
  return text
    .split(/\n[^\S\n]*\n\s*/)
    .map(paragraph => paragraph.trim())
    .filter(paragraph => paragraph.length > 0);
}

/** A language's name in the reader's language — the code itself when the browser cannot name it. */
export function languageName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: 'language' }).of(code) ?? code;
  } catch {
    return code;
  }
}

/**
 * The language a source publishes in, named without its region: two sources in one
 * language read alike, and the name never nests in a label's own parentheses
 * (« BBC 中文 (chinois (Chine)) »).
 */
export function sourceLanguageName(code: string, locale: string): string {
  const primary = code.split(/[-_]/)[0];
  return primary ? languageName(primary, locale) : code;
}
