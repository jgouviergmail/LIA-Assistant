import { describe, expect, it } from 'vitest';
import { cardTargetHref, type CardToolTarget } from '../card-target';

function target(overrides: Partial<CardToolTarget>): CardToolTarget {
  return {
    kind: 'email',
    item_id: 'item &/=%?',
    container_id: 'container &/=%?',
    day: null,
    is_folder: false,
    ...overrides,
  };
}

describe('verified item addresses', () => {
  it.each([
    ['email', 'mail', { id: 'item &/=%?', folder: 'container &/=%?' }],
    ['event', 'calendar', { cal: 'container &/=%?', event: 'item &/=%?', day: '2026-11-08' }],
    ['calendar', 'calendar', { cal: 'item &/=%?' }],
    ['contact', 'contacts', { contact: 'item &/=%?' }],
    ['task', 'tasks', { list: 'container &/=%?', task: 'item &/=%?' }],
    ['file', 'files', { file: 'item &/=%?' }],
    ['hue_light', 'lights', { light: 'item &/=%?' }],
  ] as const)('opens %s with exact encoded scope and no invented field', (kind, tool, query) => {
    const href = cardTargetHref(
      target({ kind, day: kind === 'event' ? '2026-11-08' : null }),
      'en',
      'opaque.signed-token'
    );
    expect(href).not.toBeNull();
    const url = new URL(href!, 'https://lia.test');
    expect(url.pathname).toBe(`/en/dashboard/tools/${tool}`);
    expect(Object.fromEntries(url.searchParams)).toEqual({
      ...query,
      card_source: 'opaque.signed-token',
    });
  });

  it('opens a real folder and leaves an absent mail folder absent', () => {
    expect(
      cardTargetHref(target({ kind: 'file', item_id: 'folder', is_folder: true }), 'fr', 'proof')
    ).toBe('/dashboard/tools/files?folder=folder&card_source=proof');
    expect(cardTargetHref(target({ item_id: 'mail', container_id: null }), 'de', 'proof')).toBe(
      '/de/dashboard/tools/mail?id=mail&card_source=proof'
    );
  });

  it.each(['event', 'task'] as const)('refuses an unscoped %s', kind => {
    expect(cardTargetHref(target({ kind, container_id: null }), 'en', 'proof')).toBeNull();
  });

  it.each([
    {},
    { ...target({}), kind: 'other' },
    { ...target({}), item_id: '' },
    { ...target({}), day: '2026-02-30' },
  ])('refuses malformed wire data', value => {
    expect(cardTargetHref(value, 'en', 'proof')).toBeNull();
  });
});
