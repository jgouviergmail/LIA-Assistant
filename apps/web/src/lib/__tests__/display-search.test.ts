import { describe, expect, it } from 'vitest';
import corpus from './fixtures/display-search.json';
import { normalizeSearchText } from '../utils';

describe('shared display search corpus', () => {
  it.each(corpus)('normalizes %s without changing identity semantics', (source, expected) => {
    expect(normalizeSearchText(source)).toBe(expected);
  });
});
