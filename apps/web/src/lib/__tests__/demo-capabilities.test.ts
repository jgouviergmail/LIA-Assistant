import { describe, it, expect } from 'vitest';

import { readPublicCapabilities } from '@/lib/demo-capabilities';

describe('readPublicCapabilities', () => {
  it('keeps every well-formed entry and drops the rest', () => {
    expect(
      readPublicCapabilities({
        web_search: { enabled: true, family: 'reach' },
        broken: { enabled: 'yes', family: 'reach' },
        other: 'nope',
      })
    ).toEqual({ web_search: { enabled: true, family: 'reach' } });
  });

  it('answers null — "did not answer" — for an absent, empty or malformed block', () => {
    expect(readPublicCapabilities(undefined)).toBeNull();
    expect(readPublicCapabilities(null)).toBeNull();
    expect(readPublicCapabilities({})).toBeNull();
    expect(readPublicCapabilities('text')).toBeNull();
    expect(readPublicCapabilities({ only: { enabled: 1 } })).toBeNull();
  });
});
