/**
 * The articles a session cited (ADR-324): each story once, in the order it
 * first aired — a panel the listener opened stays where it is while the
 * programme moves on — and the listener's own records never offered as one.
 */
import { describe, expect, it } from 'vitest';

import {
  languageName,
  paragraphs,
  sourceLanguageName,
  withArticles,
  type RadioArticleRef,
} from '../articles';
import type { RadioSegment, RadioSource } from '../types';

function source(label: string, articleId: string | null): RadioSource {
  return {
    label,
    url: `https://news.example/${label}`,
    published_at: '2026-09-26T08:00:00Z',
    article_id: articleId,
  };
}

function segment(seq: number, ...sources: RadioSource[][]): RadioSegment {
  return {
    seq,
    format: 'headlines',
    mood: 'news',
    title: `S${seq}`,
    duration_s: 60,
    transcript: sources.map((cited, index) => ({
      role: 'anchor',
      text: `Line ${index}`,
      offset_s: index * 5,
      sources: cited,
    })),
  };
}

describe('withArticles', () => {
  it('adds a segment’s stories in the order they are cited, each once', () => {
    const heard = withArticles(
      [],
      segment(1, [source('A', 'a1'), source('B', 'b1')], [source('A', 'a1')], [source('C', 'c1')])
    );
    expect(heard).toEqual<RadioArticleRef[]>([
      { id: 'a1', outlet: 'A', url: 'https://news.example/A', publishedAt: '2026-09-26T08:00:00Z' },
      { id: 'b1', outlet: 'B', url: 'https://news.example/B', publishedAt: '2026-09-26T08:00:00Z' },
      { id: 'c1', outlet: 'C', url: 'https://news.example/C', publishedAt: '2026-09-26T08:00:00Z' },
    ]);
  });

  it('keeps what was heard in place and appends only the new stories', () => {
    const first = withArticles([], segment(1, [source('A', 'a1')]));
    const second = withArticles(first, segment(2, [source('B', 'b1'), source('A', 'a1')]));
    expect(second.map(article => article.id)).toEqual(['a1', 'b1']);
  });

  it('never offers a source that is no story — the listener’s own records', () => {
    expect(withArticles([], segment(1, [source('Calendar', null)]))).toEqual([]);
  });

  it('hands back the same list when a segment cites nothing new', () => {
    const first = withArticles([], segment(1, [source('A', 'a1')]));
    expect(withArticles(first, segment(2, [source('A', 'a1')], []))).toBe(first);
  });
});

describe('paragraphs', () => {
  it('splits the text at its blank lines and keeps a line break inside a paragraph', () => {
    expect(paragraphs('First.\n\nSecond,\nsame paragraph.\n \n\nThird.')).toEqual([
      'First.',
      'Second,\nsame paragraph.',
      'Third.',
    ]);
  });

  it('has nothing to show for an empty text', () => {
    expect(paragraphs('  \n\n ')).toEqual([]);
  });
});

describe('languageName', () => {
  it('names a language in the reader’s own language', () => {
    expect(languageName('en', 'fr')).toBe('anglais');
    expect(languageName('de', 'en')).toBe('German');
  });

  it('falls back on the code when the browser cannot name it', () => {
    expect(languageName('not a code!', 'en')).toBe('not a code!');
  });
});

describe('sourceLanguageName', () => {
  it('names the language a source publishes in, without its region', () => {
    // « BBC 中文 (chinois (Chine)) » nested one pair of parentheses in another.
    expect(languageName('zh-CN', 'fr')).toBe('chinois (Chine)');
    expect(sourceLanguageName('zh-CN', 'fr')).toBe('chinois');
    expect(sourceLanguageName('en_US', 'en')).toBe('English');
    expect(sourceLanguageName('pt', 'it')).toBe('portoghese');
  });

  it('falls back on the code when the browser cannot name it', () => {
    expect(sourceLanguageName('not a code!', 'en')).toBe('not a code!');
  });
});
