/**
 * Copying a text (ADR-369, lot 2): a page with no clipboard copies through its selection, and when
 * nothing takes the text it refuses; it never throws through the click that asked.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copyText } from '../copy';

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, 'execCommand');
});

function selectionCopies(copied: boolean) {
  const execCommand = vi.fn().mockReturnValue(copied);
  Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand });
  return execCommand;
}

describe('copyText', () => {
  it('hands the text to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    await copyText('words');

    expect(writeText).toHaveBeenCalledWith('words');
  });

  it('copies through the page where it has no clipboard, leaving nothing behind', async () => {
    vi.stubGlobal('navigator', {});
    const execCommand = selectionCopies(true);
    const field = document.body.appendChild(document.createElement('input'));
    field.focus();

    await copyText('words');

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(document.querySelector('textarea')).toBeNull();
    expect(document.activeElement).toBe(field);
    field.remove();
  });

  it('refuses when nothing took the text', async () => {
    vi.stubGlobal('navigator', {});
    selectionCopies(false);

    await expect(copyText('words')).rejects.toThrow('clipboard_unavailable');
  });

  it('refuses where the page cannot copy at all', async () => {
    vi.stubGlobal('navigator', {});

    await expect(copyText('words')).rejects.toThrow('clipboard_unavailable');
  });
});
