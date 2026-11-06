/**
 * What the API answers of a document, by the type it declares (ADR-369, lot 14): each type names
 * the viewer that reads it, and bytes reach the viewers whole, whatever the page might sniff.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { getResponse: vi.fn() } }));
vi.mock('@/lib/api-client', () => ({ default: api }));

import { shownOf } from '../shown';

const WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

function answers(body: BodyInit, type: string, cut = false): void {
  api.getResponse.mockResolvedValue(
    new Response(body, {
      headers: { 'Content-Type': type, 'X-Preview-Truncated': String(cut) },
    })
  );
}

function reading(): ReturnType<typeof shownOf> {
  return shownOf('/workbench/files/preview', { id: 'f1' }, new AbortController().signal);
}

describe('shownOf', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'URL',
      Object.assign(URL, { createObjectURL: vi.fn().mockReturnValue('blob:one') })
    );
  });

  it('asks for the document, under the read it can be dropped with', async () => {
    answers('hello', 'text/plain');
    const stop = new AbortController();

    await shownOf('/workbench/files/preview', { id: 'f1' }, stop.signal);

    expect(api.getResponse).toHaveBeenCalledWith('/workbench/files/preview', {
      params: { id: 'f1' },
      signal: stop.signal,
    });
  });

  it('keeps an image as an address the page draws', async () => {
    answers('png', 'image/png');

    expect(await reading()).toEqual({ kind: 'image', url: 'blob:one' });
  });

  it.each([
    ['pdf', 'application/pdf'],
    ['word', WORD],
  ])('hands a %s to its viewer as bytes', async (kind, type) => {
    answers('bytes', type);

    const shown = await reading();

    expect(shown.kind).toBe(kind);
    if (shown.kind !== 'pdf' && shown.kind !== 'word') throw new Error('no bytes');
    expect(await shown.data.text()).toBe('bytes');
  });

  it('says a Markdown is one, with its cut', async () => {
    answers('# Title', 'text/markdown; charset=utf-8', true);

    expect(await reading()).toEqual({ kind: 'markdown', text: '# Title', cut: true });
  });

  it('reads tables', async () => {
    const sheets = [{ name: 'Budget', rows: [['A']], cut: false }];
    answers(JSON.stringify({ sheets }), 'application/json');

    expect(await reading()).toEqual({ kind: 'sheets', sheets, cut: false });
  });

  it('takes anything else as words', async () => {
    answers('<b>hello</b>', 'text/plain; charset=utf-8');

    expect(await reading()).toEqual({ kind: 'text', text: '<b>hello</b>', cut: false });
  });
});
