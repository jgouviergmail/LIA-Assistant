/**
 * downloadMarkdown — client-side export of an assistant response as a `.md`
 * file (UX P4). The oracle is the full anchor protocol: a UTF-8 markdown blob,
 * a sanitised dated filename, a programmatic click, and the cleanup that keeps
 * it leak-free (anchor removed, object URL revoked).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { downloadMarkdown } from '../download-markdown';

const createObjectURL = vi.fn((_blob: Blob) => 'blob:md-export');
const revokeObjectURL = vi.fn();
let clickSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
  clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
});

afterEach(() => {
  clickSpy.mockRestore();
});

/** The anchor observed at click time (it is removed from the DOM right after). */
function clickedAnchor(): HTMLAnchorElement {
  expect(clickSpy).toHaveBeenCalledTimes(1);
  return clickSpy.mock.instances[0] as unknown as HTMLAnchorElement;
}

describe('downloadMarkdown', () => {
  it('downloads a .md file named after the sanitised base name', () => {
    downloadMarkdown('# Plan', 'lia-2026-07-28-19-42');

    const anchor = clickedAnchor();
    expect(anchor.download).toBe('lia-2026-07-28-19-42.md');
    expect(anchor.getAttribute('href')).toBe('blob:md-export');
  });

  it('preserves the markdown content and its accents as UTF-8', async () => {
    const content = '# Été\n\nRéponse **markdown** avec accents : à, ç, ü.';
    downloadMarkdown(content, 'export');

    const blob = createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe('text/markdown;charset=utf-8');
    await expect(blob.text()).resolves.toBe(content);
  });

  it('falls back to "lia" when the base name sanitises to nothing', () => {
    downloadMarkdown('contenu', '🚀✨');
    expect(clickedAnchor().download).toBe('lia.md');
  });

  it('cleans up after itself: anchor removed, object URL revoked', () => {
    downloadMarkdown('contenu', 'export');
    expect(document.querySelector('a[download]')).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:md-export');
  });
});
