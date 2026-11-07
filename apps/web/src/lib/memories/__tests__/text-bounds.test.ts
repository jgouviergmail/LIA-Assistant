/**
 * text-bounds — what the memory form holds a text to, ahead of the API.
 *
 * The count is the contract: the API refuses by code points, so a form counting
 * `String.length` would block a text the API accepts and let the person believe a
 * saved memory is too long. An emoji is the case that tells the two apart.
 */

import { describe, it, expect } from 'vitest';

import {
  countCharacters,
  excessCharacters,
  isMemoryTextSavable,
  isRefusedInput,
  isTooShort,
  memoryTextBounds,
} from '../text-bounds';
import type { MemoryLimits } from '@/hooks/useMemories';

const LIMITS: MemoryLimits = {
  content_min_chars: 3,
  content_max_chars: 500,
  trigger_topic_max_chars: 100,
  usage_nuance_max_chars: 300,
};

const form = (over: Partial<Parameters<typeof isMemoryTextSavable>[0]> = {}) => ({
  content: 'A valid fact',
  trigger_topic: '',
  usage_nuance: '',
  ...over,
});

describe('countCharacters', () => {
  it.each([
    ['', 0],
    ['abc', 3],
    ['é', 1],
    ['😀', 1],
    ['😀😀', 2],
    // A combining accent and a family emoji are several code points, for the API too.
    ['é', 2],
    ['👨‍👩‍👧', 5],
  ])('counts %j as the API does', (text, expected) => {
    expect(countCharacters(text)).toBe(expected);
  });
});

describe('memoryTextBounds', () => {
  it('reads each bound from what the API published', () => {
    expect(memoryTextBounds(LIMITS)).toEqual({
      content: { min: 3, max: 500 },
      trigger_topic: { min: 0, max: 100 },
      usage_nuance: { min: 0, max: 300 },
    });
  });
});

describe('excessCharacters', () => {
  const bound = { min: 3, max: 500 };

  it.each([
    [495, 0],
    [500, 0],
    [501, 1],
    [512, 12],
  ])('a text of %i characters is %i past the ceiling', (length, excess) => {
    expect(excessCharacters('x'.repeat(length), bound)).toBe(excess);
  });

  it('never counts an emoji twice', () => {
    expect(excessCharacters('😀'.repeat(500), bound)).toBe(0);
  });
});

describe('isTooShort', () => {
  const bound = { min: 3, max: 500 };

  it('leaves an empty field alone: nobody has typed anything to refuse yet', () => {
    expect(isTooShort('', bound)).toBe(false);
  });

  it.each([
    ['a', true],
    ['ab', true],
    ['abc', false],
  ])('%j under a floor of 3 is %s', (text, expected) => {
    expect(isTooShort(text, bound)).toBe(expected);
  });
});

describe('isRefusedInput', () => {
  it('recognises what the API refused, by its status', () => {
    expect(isRefusedInput(Object.assign(new Error('refused'), { status: 422 }))).toBe(true);
  });

  it.each([
    ['a server failure', Object.assign(new Error('down'), { status: 500 })],
    ['a transport failure', new Error('network')],
    ['anything else', 'text'],
    ['nothing', null],
  ])('leaves %s to the generic message', (_case, error) => {
    expect(isRefusedInput(error)).toBe(false);
  });
});

describe('isMemoryTextSavable', () => {
  it('accepts a text at each ceiling', () => {
    expect(
      isMemoryTextSavable(
        form({
          content: 'x'.repeat(500),
          trigger_topic: 'x'.repeat(100),
          usage_nuance: 'x'.repeat(300),
        }),
        LIMITS
      )
    ).toBe(true);
  });

  it.each([
    ['content', 501],
    ['trigger_topic', 101],
    ['usage_nuance', 301],
  ])('refuses %s past its ceiling', (field, length) => {
    expect(isMemoryTextSavable(form({ [field]: 'x'.repeat(length) }), LIMITS)).toBe(false);
  });

  it('refuses a content under its floor', () => {
    expect(isMemoryTextSavable(form({ content: 'ab' }), LIMITS)).toBe(false);
  });

  it.each([[''], ['   ']])('refuses a content of nothing but %j', content => {
    expect(isMemoryTextSavable(form({ content }), LIMITS)).toBe(false);
  });

  it('accepts empty optional texts: a cleared nuance is a choice', () => {
    expect(isMemoryTextSavable(form({ trigger_topic: '', usage_nuance: '' }), LIMITS)).toBe(true);
  });

  it('asks only for some content while the limits are unknown: the API still decides', () => {
    expect(isMemoryTextSavable(form({ content: 'x'.repeat(9_999) }), undefined)).toBe(true);
    expect(isMemoryTextSavable(form({ content: ' ' }), undefined)).toBe(false);
  });
});
