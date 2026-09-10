/**
 * What an operator types and what LIA stores (ADR-278).
 *
 * The field speaks k because that is how a context window is named everywhere
 * else; the column stores tokens because that is what the server is asked for.
 * These two functions are the only place the units meet.
 */

import { describe, expect, it } from 'vitest';

import { TOKENS_PER_K, fromK, toK } from '@/lib/llm-config/context-window';

describe('toK', () => {
  it('reads a power-of-two window as a round number', () => {
    expect(toK(32768)).toBe(32);
    expect(toK(262144)).toBe(256);
    expect(toK(4096)).toBe(4);
  });

  it('keeps one decimal for a window that is not a round k', () => {
    expect(toK(100000)).toBe(97.7);
  });

  it('is a BINARY k, like every context window', () => {
    // Measured: at one decimal, 1 000 and 1 024 both READ as « 1 k ». That is
    // fine going out — no context window is 1 000 — but the way BACK must not
    // lose the binary k, which is what the round-trip below pins.
    expect(TOKENS_PER_K).toBe(1024);
    expect(fromK('1')).toBe(1024);
    expect(fromK('128')).toBe(131072);
  });
});

describe('fromK', () => {
  it('stores tokens for a round k', () => {
    expect(fromK('32')).toBe(32768);
    expect(fromK('256')).toBe(262144);
  });

  it('accepts a comma as the decimal mark', () => {
    // Four of the six locales write 32,5.
    expect(fromK('32,5')).toBe(fromK('32.5'));
    expect(fromK('32,5')).toBe(33280);
  });

  it.each(['', '   ', 'abc', '0', '-4', 'NaN', 'Infinity'])(
    'reads %p as « use the model’s own »',
    raw => {
      expect(fromK(raw)).toBeNull();
    }
  );

  it('round-trips every value a field can show', () => {
    for (const tokens of [4096, 8192, 32768, 131072, 262144]) {
      expect(fromK(String(toK(tokens)))).toBe(tokens);
    }
  });

  it('never returns a fractional token count', () => {
    const stored = fromK('32,7');
    expect(stored).not.toBeNull();
    expect(Number.isInteger(stored)).toBe(true);
  });
});
