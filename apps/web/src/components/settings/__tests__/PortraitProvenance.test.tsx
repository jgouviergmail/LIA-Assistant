/**
 * What the portrait was compiled from (2026-09-16 design, part B): one line
 * naming the entries and each source that was USED with the count it gave,
 * a switched-off source omitted, an unavailable source named on a second
 * line. Counts come from the payload — nothing is computed here.
 */

import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import en from '@/../locales/en/translation.json';
import fr from '@/../locales/fr/translation.json';
import zh from '@/../locales/zh/translation.json';
import type { PortraitProvenance as Provenance } from '@/hooks/useJournals';

import { PortraitProvenance } from '../PortraitProvenance';

function provenance(over: Partial<Provenance> = {}): Provenance {
  return {
    version: 1,
    journal_entries: 12,
    sources: {
      memories: { status: 'used', used: 34, total: 51 },
      interests: { status: 'used', used: 8, total: 8 },
      habits: { status: 'disabled', used: 0, total: 0 },
      relation_debriefs: { status: 'unavailable', used: 0, total: 0 },
    },
    ...over,
  };
}

describe('PortraitProvenance', () => {
  it('names the entries and every source that was used, with the payload counts', () => {
    renderWithProviders(<PortraitProvenance provenance={provenance()} lng="en" />);
    const line = screen.getByTestId('portrait-provenance');
    expect(line).toHaveTextContent('journals.provenance.compiled_from');
    // The fragments the line was built from carry the payload's numbers.
    expect(line.getAttribute('data-parts')).toBe('entries:12|memories:34|interests:8');
  });

  it('names an unavailable source on its own line and omits a switched-off one', () => {
    renderWithProviders(<PortraitProvenance provenance={provenance()} lng="en" />);
    const unavailable = screen.getByTestId('portrait-provenance-unavailable');
    expect(unavailable.getAttribute('data-sources')).toBe('relation_debriefs');
    expect(screen.getByTestId('portrait-provenance').getAttribute('data-parts')).not.toContain(
      'habits'
    );
  });

  it('draws no second line when every source could be read', () => {
    const all = provenance({
      sources: {
        memories: { status: 'used', used: 1, total: 1 },
        interests: { status: 'empty', used: 0, total: 0 },
        habits: { status: 'used', used: 2, total: 2 },
        relation_debriefs: { status: 'disabled', used: 0, total: 0 },
      },
    });
    renderWithProviders(<PortraitProvenance provenance={all} lng="fr" />);
    expect(screen.queryByTestId('portrait-provenance-unavailable')).not.toBeInTheDocument();
    expect(screen.getByTestId('portrait-provenance').getAttribute('data-parts')).toBe(
      'entries:12|memories:1|habits:2'
    );
  });

  it('names the five records that joined on 2026-10-12, in the declared order', () => {
    const nine = provenance({
      sources: {
        memories: { status: 'used', used: 62, total: 62 },
        interests: { status: 'empty', used: 0, total: 0 },
        habits: { status: 'used', used: 2, total: 2 },
        relation_debriefs: { status: 'used', used: 3, total: 3 },
        open_loops: { status: 'used', used: 4, total: 4 },
        workboard: { status: 'used', used: 4, total: 4 },
        routines: { status: 'used', used: 3, total: 3 },
        reminders: { status: 'unavailable', used: 0, total: 0 },
        bookmarks: { status: 'used', used: 3, total: 3 },
      },
    });
    renderWithProviders(<PortraitProvenance provenance={nine} lng="en" />);
    expect(screen.getByTestId('portrait-provenance').getAttribute('data-parts')).toBe(
      'entries:12|memories:62|habits:2|relation_debriefs:3|open_loops:4|workboard:4|routines:3|bookmarks:3'
    );
    expect(screen.getByTestId('portrait-provenance-unavailable').getAttribute('data-sources')).toBe(
      'reminders'
    );
    expect(en.journals.provenance.open_loops_other).toBe('{{count}} open loops');
    expect(zh.journals.provenance.bookmarks_one).toBe(zh.journals.provenance.bookmarks_other);
  });

  it('names a source the compilation window cut, and never lists one it kept nothing of', () => {
    const cutOne = provenance({
      sources: {
        memories: { status: 'used', used: 40, total: 62, reason: 'over_budget' },
        interests: { status: 'used', used: 0, total: 9, reason: 'over_budget' },
        habits: { status: 'used', used: 2, total: 2 },
        relation_debriefs: { status: 'empty', used: 0, total: 0 },
      },
    });
    renderWithProviders(<PortraitProvenance provenance={cutOne} lng="en" />);
    expect(screen.getByTestId('portrait-provenance').getAttribute('data-parts')).toBe(
      'entries:12|memories:40|habits:2'
    );
    expect(screen.getByTestId('portrait-provenance-cut').getAttribute('data-sources')).toBe(
      'memories|interests'
    );
    expect(en.journals.provenance.over_budget_other).toContain('{{sources}}');
    expect(zh.journals.provenance.over_budget_one).toBe(zh.journals.provenance.over_budget_other);
  });

  it('keeps the six-language contract: plurals in English, one form in Chinese', () => {
    expect(en.journals.provenance.memories_one).toBe('{{count}} memory');
    expect(en.journals.provenance.memories_other).toBe('{{count}} memories');
    expect(fr.journals.provenance.memories_other).toBe('{{count}} souvenirs');
    expect(zh.journals.provenance.memories_one).toBe(zh.journals.provenance.memories_other);
    expect(en.journals.provenance.compiled_from).toContain('{{list}}');
    expect(en.journals.provenance.unavailable_other).toContain('{{sources}}');
  });
});
