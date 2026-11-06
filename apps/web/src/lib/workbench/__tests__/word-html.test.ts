/**
 * A Word file as HTML, through the library itself and files Word's own format holds
 * (`e2e/fixtures/viewers`, ADR-369, lot 14). What it builds is somebody else's: an alternative
 * chunk, HTML the library would draw in a frame of the page, stays out, and nothing here reaches
 * further than the bytes it was given.
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { wordHtml } from '../word-html';

async function fixture(name: string): Promise<Blob> {
  const bytes = await readFile(join(process.cwd(), 'e2e/fixtures/viewers', name));
  return new Blob([new Uint8Array(bytes)]);
}

describe('wordHtml', () => {
  it('lays out what the file holds', async () => {
    const html = await wordHtml(await fixture('report.docx'));

    expect(html).toContain('Proof report');
    expect(html).toContain('<table');
    expect(html).toContain('href="https://example.org/report"');
  });

  it('carries its images inside itself', async () => {
    const html = await wordHtml(await fixture('report.docx'));

    expect(html).toContain('src="data:image/png;base64,');
    expect(html).not.toContain('blob:');
  });

  it('draws no alternative chunk', async () => {
    const html = await wordHtml(await fixture('hostile.docx'));

    expect(html).toContain('Hostile words');
    expect(html).not.toContain('<iframe');
    expect(html).not.toContain('parent.alert(2)');
  });

  it('lays its paper out to the width it is given', async () => {
    const html = await wordHtml(await fixture('report.docx'));

    expect(html).not.toMatch(/<section[^>]*style="[^"]*\bwidth:/);
  });

  it('refuses what is no Word file', async () => {
    await expect(wordHtml(new Blob(['no archive']))).rejects.toThrow();
  });
});
