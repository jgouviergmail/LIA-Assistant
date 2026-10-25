import { describe, expect, it } from 'vitest';

import { formatAttachSource, parseAttachSource } from '../attach-source-link';

const ID = '11111111-2222-4333-8444-555555555555';

describe('attach sources', () => {
  it('reads back what it wrote, for both kinds', () => {
    for (const kind of ['bookmark', 'generated'] as const) {
      expect(parseAttachSource(formatAttachSource({ kind, id: ID }))).toEqual({ kind, id: ID });
    }
  });

  it.each([
    ['nothing', null],
    ['no kind', ID],
    ['an unknown kind', `upload:${ID}`],
    ['an id that is not one', 'bookmark:../../etc'],
    ['a second part', `bookmark:${ID}:x`],
  ])('names nothing for %s', (_case, value) => {
    expect(parseAttachSource(value)).toBeNull();
  });
});
