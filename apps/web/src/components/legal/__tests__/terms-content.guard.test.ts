/**
 * The terms exist in every supported language, with the same skeleton.
 *
 * The renderer strips everything before the first `## 1.` and assigns the
 * table-of-contents anchors to the h2 headings BY POSITION (see
 * `GuideMarkdown`). A language with one section missing, one extra, or one
 * out of order would therefore not merely read badly: every anchor and icon
 * after the discrepancy would point at the wrong section, silently.
 *
 * That coupling is invisible in a translation review, so it is pinned here.
 */

import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

import { languages } from '@/i18n/settings';

const GUIDES_DIR = path.join(process.cwd(), 'src', 'data', 'guides');

/** The TOC section ids the renderer maps onto h2 headings, in order. */
const EXPECTED_SECTION_COUNT = 12;

function readTerms(lng: string): string {
  // Line endings are normalized: the two oldest files are CRLF and the newer
  // ones LF, and every structural check below anchors on "\n".
  return fs
    .readFileSync(path.join(GUIDES_DIR, `terms.${lng}.md`), 'utf-8')
    .replace(/\r\n/g, '\n');
}

function numberedHeadings(content: string): string[] {
  return content.split('\n').filter(line => /^## \d+\./.test(line));
}

describe('terms of service — every supported language', () => {
  it.each(languages)('%s has its own file (no silent English fallback)', lng => {
    expect(fs.existsSync(path.join(GUIDES_DIR, `terms.${lng}.md`))).toBe(true);
  });

  it.each(languages)('%s carries exactly the expected sections, in order', lng => {
    const headings = numberedHeadings(readTerms(lng));
    expect(headings).toHaveLength(EXPECTED_SECTION_COUNT);
    // Anchors are assigned by position: 1..12 must appear in that order.
    const numbers = headings.map(h => Number(h.match(/^## (\d+)\./)?.[1]));
    expect(numbers).toEqual(Array.from({ length: EXPECTED_SECTION_COUNT }, (_, i) => i + 1));
  });

  it.each(languages)('%s starts with a body the renderer can find', lng => {
    // `GuideMarkdown` looks for "\n## <digit>." to cut the front matter; a file
    // whose first section is not numbered would render the header and the raw
    // table of contents instead of the terms.
    expect(readTerms(lng)).toMatch(/\n## 1\./);
  });

  it.each(languages)('%s documents the public demonstration instance in full', lng => {
    const content = readTerms(lng);
    // Bounded at the closing rule: the footer ("last updated", "contact")
    // is also bold and would inflate the count.
    const fromHeading = content.slice(content.lastIndexOf('\n## 12.'));
    const closingRule = fromHeading.lastIndexOf('\n---\n');
    const lastSection = closingRule > 0 ? fromHeading.slice(0, closingRule) : fromHeading;
    // Counted by STRUCTURE, not by length: Chinese says the same thing in a
    // third of the characters, so a character threshold would fail a correct
    // translation. The section carries nine bold-led paragraphs, one per
    // commitment a visitor accepts (purpose, erasure, data not to entrust,
    // email, no linking, capacity, fair use, no warranty, alternative).
    const boldParagraphs = lastSection.match(/^\*\*[^*]+\*\*/gm) ?? [];
    expect(boldParagraphs).toHaveLength(9);
    expect(lastSection).toMatch(/AGPL-3\.0/);
  });

  it.each(languages)('%s keeps a single trailing separator', lng => {
    // Two consecutive rules render as an empty section divider.
    expect(readTerms(lng)).not.toMatch(/\n---\n---\n/);
  });
});
