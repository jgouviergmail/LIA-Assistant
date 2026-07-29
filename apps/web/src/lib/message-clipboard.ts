/**
 * Clipboard/share flattening for assistant messages (ADR-177).
 *
 * In `html` display mode the raw message content is a `lia-response` HTML
 * document; copying it verbatim pastes markup. HTML content is written as a
 * dual-flavor ClipboardItem (text/html for rich targets like mail composers,
 * text/plain for editors), with a plain-text fallback when ClipboardItem or
 * write() is unavailable (older Firefox, permission denials). Markdown content
 * is copied verbatim — flattening it would destroy intentional formatting.
 */
import { htmlToPlainText, looksLikeHtml } from './html-plain-text';

/** Flatten assistant HTML to readable text; pass anything else through. */
export function messageToPlainText(content: string): string {
  return looksLikeHtml(content) ? htmlToPlainText(content) : content;
}

/**
 * Copy an assistant message to the clipboard, flattening HTML content.
 *
 * @param content - Raw message content (markdown or lia-response HTML).
 * @throws When every clipboard write path fails — callers keep their existing
 *   try/catch + error toast.
 */
export async function copyMessageToClipboard(content: string): Promise<void> {
  if (!looksLikeHtml(content)) {
    await navigator.clipboard.writeText(content);
    return;
  }
  const plain = htmlToPlainText(content);
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([content], { type: 'text/html' }),
          'text/plain': new Blob([plain], { type: 'text/plain' }),
        }),
      ]);
      return;
    } catch {
      // Flavor/permission rejection (Safari, locked-down contexts): the
      // plain-text fallback below still delivers a useful copy.
    }
  }
  await navigator.clipboard.writeText(plain);
}
