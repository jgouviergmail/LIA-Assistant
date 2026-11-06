/**
 * Copying a text (ADR-369, lot 2): a page with no clipboard refuses, it never throws
 * through the click that asked.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copyText } from '../copy';

afterEach(() => vi.unstubAllGlobals());

describe('copyText', () => {
  it('hands the text to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    await copyText('words');

    expect(writeText).toHaveBeenCalledWith('words');
  });

  it('refuses where the page has no clipboard', async () => {
    vi.stubGlobal('navigator', {});

    await expect(copyText('words')).rejects.toBeInstanceOf(TypeError);
  });
});
