/**
 * Section keys derived from headings must satisfy the API pattern
 * `^[a-z][a-z0-9_]{1,39}$` and stay unique within a template.
 */

import { describe, expect, it } from 'vitest';

import { slugifySectionLabel, uniqueSectionKey } from '../template-keys';

const API_PATTERN = /^[a-z][a-z0-9_]{1,39}$/;

describe('slugifySectionLabel', () => {
  it.each([
    ['Résumé', 'resume'],
    ['Actions et échéances', 'actions_et_echeances'],
    ['Risques / points de vigilance', 'risques_points_de_vigilance'],
    ['  Décisions  ', 'decisions'],
    ['2 prochaines étapes', 'section_2_prochaines_etapes'],
    ['!!!', 'section'],
    ['会议纪要', 'section'],
    ['A', 'section'],
  ])('%s → %s', (label, expected) => {
    const slug = slugifySectionLabel(label);
    expect(slug).toBe(expected);
    expect(slug).toMatch(API_PATTERN);
  });

  it('caps the key at the API length', () => {
    const slug = slugifySectionLabel('a'.repeat(80));
    expect(slug).toHaveLength(40);
    expect(slug).toMatch(API_PATTERN);
  });
});

describe('uniqueSectionKey', () => {
  it('suffixes a colliding key without ever exceeding the length cap', () => {
    expect(uniqueSectionKey('Résumé', ['resume'])).toBe('resume_2');
    expect(uniqueSectionKey('Résumé', ['resume', 'resume_2'])).toBe('resume_3');
    const long = uniqueSectionKey('b'.repeat(80), ['b'.repeat(40)]);
    expect(long).toHaveLength(40);
    expect(long.endsWith('_2')).toBe(true);
    expect(long).toMatch(API_PATTERN);
  });

  it('returns the plain slug when nothing collides', () => {
    expect(uniqueSectionKey('Décisions', ['resume'])).toBe('decisions');
  });
});
