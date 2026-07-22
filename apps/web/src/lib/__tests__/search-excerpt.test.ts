/**
 * buildSearchExcerpt — plain-text excerpt around the first match (QW-2).
 */
import { describe, expect, it } from 'vitest';

import { buildSearchExcerpt } from '../search-excerpt';

describe('buildSearchExcerpt', () => {
  it('returns the match with its surrounding window', () => {
    const excerpt = buildSearchExcerpt('Bonjour, la réunion de demain est confirmée.', 'reunion');

    expect(excerpt).toEqual({
      prefix: 'Bonjour, la ',
      match: 'réunion',
      suffix: ' de demain est confirmée.',
    });
  });

  it('elides long sides with ellipses', () => {
    const long = `${'a'.repeat(100)} pizza ${'b'.repeat(100)}`;

    const excerpt = buildSearchExcerpt(long, 'pizza', 10);

    expect(excerpt?.prefix.startsWith('…')).toBe(true);
    expect(excerpt?.prefix.length).toBeLessThanOrEqual(11);
    expect(excerpt?.match).toBe('pizza');
    expect(excerpt?.suffix.endsWith('…')).toBe(true);
  });

  it('strips HTML before matching (assistant bubbles are HTML)', () => {
    const excerpt = buildSearchExcerpt(
      '<div class="lia-response"><p>Ta <strong>pizza</strong> arrive.</p></div>',
      'pizza'
    );

    expect(excerpt?.match).toBe('pizza');
    expect(excerpt?.prefix).toContain('Ta ');
    expect(excerpt?.prefix).not.toContain('<');
  });

  it('returns null when the term only matched markup', () => {
    const excerpt = buildSearchExcerpt('<div data-x="pizza">rien ici</div>', 'pizza');

    expect(excerpt).toBeNull();
  });

  it('returns null for empty queries or no match', () => {
    expect(buildSearchExcerpt('contenu', '  ')).toBeNull();
    expect(buildSearchExcerpt('contenu', 'absent')).toBeNull();
  });
});
