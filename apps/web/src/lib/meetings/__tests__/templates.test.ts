/**
 * Library helpers (ADR-259): grouping by category in library order, and what a
 * template is for the UI (transcript templates are long and paid like a rewrite).
 */

import { describe, expect, it } from 'vitest';

import type { MeetingTemplateSummary } from '@/types/meetings';
import { TEMPLATE_CATEGORIES } from '@/types/meetings';

import {
  groupByCategory,
  isTranscriptTemplate,
  sectionsEqual,
  userTemplateCount,
} from '../templates';

function summary(over: Partial<MeetingTemplateSummary> = {}): MeetingTemplateSummary {
  return {
    ref: 'builtin:default_minutes',
    name: 'Minutes',
    description: null,
    category: 'meeting',
    builtin: true,
    sections_count: 6,
    auto_selectable: true,
    ...over,
  };
}

describe('TEMPLATE_CATEGORIES', () => {
  it("lists the eight categories with the user's own first", () => {
    expect(TEMPLATE_CATEGORIES[0]).toBe('custom');
    expect(TEMPLATE_CATEGORIES).toHaveLength(8);
    expect(new Set(TEMPLATE_CATEGORIES).size).toBe(8);
  });
});

describe('groupByCategory', () => {
  it('keeps the library order, omits empty categories and preserves item order', () => {
    const items = [
      summary({ ref: 'builtin:bant_analysis', category: 'business' }),
      summary({ ref: 'user:1', category: 'custom', builtin: false, name: 'Mine' }),
      summary({ ref: 'builtin:default_minutes', category: 'meeting' }),
      summary({ ref: 'builtin:daily_standup', category: 'meeting', name: 'Daily' }),
    ];
    const groups = groupByCategory(items);
    expect([...groups.keys()]).toEqual(['custom', 'meeting', 'business']);
    expect(groups.get('meeting')?.map(t => t.ref)).toEqual([
      'builtin:default_minutes',
      'builtin:daily_standup',
    ]);
  });

  it('returns an empty map for an empty library', () => {
    expect(groupByCategory([]).size).toBe(0);
  });
});

describe('isTranscriptTemplate / userTemplateCount', () => {
  it('flags the transcript category only', () => {
    expect(isTranscriptTemplate(summary({ category: 'transcript', auto_selectable: false }))).toBe(
      true
    );
    expect(isTranscriptTemplate(summary())).toBe(false);
  });

  it('counts the user rows, never the built-ins', () => {
    expect(
      userTemplateCount([
        summary(),
        summary({ ref: 'user:1', builtin: false }),
        summary({ ref: 'user:2', builtin: false }),
      ])
    ).toBe(2);
  });
});

describe('sectionsEqual', () => {
  const base = [
    { key: 'summary', label: 'Summary', instruction: 'Prose.', kind: 'paragraph' as const },
    { key: 'decisions', label: 'Decisions', instruction: 'Bullets.', kind: 'bullets' as const },
  ];

  it('is true for the same sections in the same order, whatever the array identity', () => {
    expect(
      sectionsEqual(
        base,
        base.map(s => ({ ...s }))
      )
    ).toBe(true);
  });

  it('is false on any field, order or length difference', () => {
    expect(sectionsEqual(base, [base[1], base[0]])).toBe(false);
    expect(sectionsEqual(base, [base[0]])).toBe(false);
    expect(sectionsEqual(base, [base[0], { ...base[1], instruction: 'Numbered.' }])).toBe(false);
    expect(sectionsEqual(base, [base[0], { ...base[1], kind: 'topics' }])).toBe(false);
  });
});
