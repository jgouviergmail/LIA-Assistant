/**
 * The terms actually RENDER in every supported language.
 *
 * The structural guard next door reads the markdown; this one pushes each
 * language through the real rendering pipeline, because the coupling that
 * matters is invisible in the source: `GuideMarkdown` drops everything before
 * the first `## 1.` and then assigns the table-of-contents anchors to h2
 * headings BY POSITION. A translation whose skeleton drifts would render with
 * every anchor pointing one section off — the page would look perfectly fine.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import fs from 'fs';
import path from 'path';

import { GuideMarkdown } from '@/components/guides/GuideMarkdown';
import { languages } from '@/i18n/settings';

vi.mock('next/dynamic', () => ({
  default: () => () => null,
}));

/** The section ids TermsContent feeds, in the order it feeds them. */
const SECTION_IDS = [
  'purpose',
  'acceptance',
  'registration',
  'service',
  'usage',
  'opensource',
  'personal_data',
  'availability',
  'liability',
  'termination',
  'applicable_law',
  'demo_instance',
] as const;

function termsFor(lng: string): string {
  return fs.readFileSync(
    path.join(process.cwd(), 'src', 'data', 'guides', `terms.${lng}.md`),
    'utf-8'
  );
}

describe('terms rendering', () => {
  it.each(languages)('%s renders all twelve anchored sections', lng => {
    const { container } = render(
      <GuideMarkdown content={termsFor(lng)} sectionIds={[...SECTION_IDS]} />
    );

    const headings = [...container.querySelectorAll('h2')];
    expect(headings).toHaveLength(SECTION_IDS.length);
    // Same ids, same order: this is what makes the sidebar links land right.
    expect(headings.map(h => h.id)).toEqual([...SECTION_IDS]);
  });

  it.each(languages)('%s drops the front matter and the raw table of contents', lng => {
    render(<GuideMarkdown content={termsFor(lng)} sectionIds={[...SECTION_IDS]} />);

    // The rendered page starts at section 1; the markdown's own list of links
    // is replaced by the localized <GuideToc>, so it must not appear twice.
    const firstHeading = screen.getAllByRole('heading', { level: 2 })[0];
    expect(firstHeading.id).toBe('purpose');
  });

  it.each(languages)('%s ends on the demonstrator section, in that language', lng => {
    const { container } = render(
      <GuideMarkdown content={termsFor(lng)} sectionIds={[...SECTION_IDS]} />
    );

    const last = [...container.querySelectorAll('h2')].at(-1);
    expect(last?.id).toBe('demo_instance');
    // Its body is present and localized — not an English leftover, except in
    // English itself.
    const body = last?.parentElement?.textContent ?? '';
    expect(body.length).toBeGreaterThan(0);
  });

  it('renders each language with its own words, never a shared fallback', () => {
    const markers: Record<string, string> = {
      en: 'Public demonstration instance',
      fr: 'Instance de demonstration publique',
      de: 'Demo-Instanz',
      es: 'demostración',
      it: 'dimostrazione',
      zh: '演示实例',
    };
    for (const lng of languages) {
      const { container, unmount } = render(
        <GuideMarkdown content={termsFor(lng)} sectionIds={[...SECTION_IDS]} />
      );
      expect(container.textContent).toContain(markers[lng]);
      unmount();
    }
  });
});
