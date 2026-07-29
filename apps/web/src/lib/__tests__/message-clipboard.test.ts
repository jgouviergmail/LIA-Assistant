/**
 * message-clipboard — copy/share flattening for assistant messages (ADR-177).
 *
 * In `html` display mode the raw message content is a `lia-response` HTML
 * document; copying it verbatim pastes markup. HTML content is written as a
 * dual-flavor ClipboardItem (text/html for rich targets, text/plain for
 * editors), with a plain-text fallback when ClipboardItem or write() is
 * unavailable. Markdown content is copied verbatim.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { copyMessageToClipboard, messageToPlainText } from '../message-clipboard';

const HTML = '<div class="lia-response"><h2>Titre</h2><p>Corps</p></div>';

describe('messageToPlainText', () => {
  it('flattens HTML and passes markdown through', () => {
    // Blocks separated by ONE empty line — backend html_to_text semantics.
    expect(messageToPlainText(HTML)).toBe('Titre\n\nCorps');
    expect(messageToPlainText('**md**')).toBe('**md**');
  });
});

describe('copyMessageToClipboard', () => {
  const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
  const write = vi.fn<(items: unknown[]) => Promise<void>>().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.stubGlobal('navigator', { clipboard: { writeText, write } });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('copies markdown content verbatim via writeText', async () => {
    await copyMessageToClipboard('**md**');
    expect(writeText).toHaveBeenCalledWith('**md**');
    expect(write).not.toHaveBeenCalled();
  });

  it('copies HTML content as a dual-flavor ClipboardItem', async () => {
    class FakeClipboardItem {
      constructor(public readonly items: Record<string, Blob>) {}
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);

    await copyMessageToClipboard(HTML);

    expect(write).toHaveBeenCalledTimes(1);
    expect(writeText).not.toHaveBeenCalled();
    const item = write.mock.calls[0][0][0] as InstanceType<typeof FakeClipboardItem>;
    expect(Object.keys(item.items).sort()).toEqual(['text/html', 'text/plain']);
    expect(await item.items['text/plain'].text()).toBe('Titre\n\nCorps');
    expect(await item.items['text/html'].text()).toBe(HTML);
  });

  it('falls back to flattened writeText when ClipboardItem is unavailable', async () => {
    vi.stubGlobal('ClipboardItem', undefined);
    await copyMessageToClipboard(HTML);
    expect(write).not.toHaveBeenCalled();
    expect(writeText).toHaveBeenCalledWith('Titre\n\nCorps');
  });

  it('falls back to flattened writeText when write() rejects', async () => {
    class FakeClipboardItem {
      constructor(public readonly items: Record<string, Blob>) {}
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    write.mockRejectedValueOnce(new Error('denied'));

    await copyMessageToClipboard(HTML);

    expect(writeText).toHaveBeenCalledWith('Titre\n\nCorps');
  });
});
