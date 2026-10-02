import { afterEach, describe, expect, it, vi } from 'vitest';

import { z } from '@/lib/zod';

describe('zod under the CSP', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('parses an object schema without ever constructing a Function (the eval probe)', () => {
    const construct = vi.spyOn(globalThis, 'Function');

    const parsed = z.object({ id: z.string(), count: z.number() }).parse({ id: 'a', count: 2 });

    expect(parsed).toEqual({ id: 'a', count: 2 });
    expect(construct).not.toHaveBeenCalled();
  });
});
