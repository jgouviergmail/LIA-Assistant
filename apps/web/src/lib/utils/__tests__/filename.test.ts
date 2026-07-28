/**
 * sanitiseFilename — the shared filename cleaner behind every client-side
 * download (images, markdown exports). Pinned on its own because two features
 * now depend on the exact same semantics: accented letters survive, separators
 * and emoji collapse to single underscores, edges are trimmed.
 */

import { describe, it, expect } from 'vitest';

import { sanitiseFilename } from '../filename';

describe('sanitiseFilename', () => {
  it('keeps letters (accents included), digits, hyphens and underscores', () => {
    expect(sanitiseFilename('Réunion été 2026 n°3')).toBe('Réunion_été_2026_n_3');
  });

  it('collapses runs of forbidden characters into a single underscore', () => {
    expect(sanitiseFilename('a / b :: c')).toBe('a_b_c');
  });

  it('trims leading and trailing underscores', () => {
    expect(sanitiseFilename('  plan.md  ')).toBe('plan_md');
  });

  it('returns an empty string when nothing survives', () => {
    expect(sanitiseFilename('🚀✨')).toBe('');
  });
});
