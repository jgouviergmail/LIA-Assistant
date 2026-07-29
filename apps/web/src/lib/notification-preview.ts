/**
 * Plain-text previews for notification surfaces (toast descriptions).
 *
 * Assistant content is rich: an HTML document wrapped in
 * `<div class="lia-response">` when the user's display mode is `html`,
 * server-rendered data cards otherwise, Markdown in between. The chat renders
 * that through the ReactMarkdown + rehypeRaw pipeline, but a toast description
 * is plain React children — markup shows up as literal text
 * (`<div class="lia-response"><h2>…`).
 *
 * The backend already flattens the bodies it controls; this is the client-side
 * half of the same guard, covering every notification type uniformly (proactive
 * and reminder payloads keep their Markdown for the chat message and must only
 * be flattened for the preview).
 *
 * Detection and flattening live in `html-plain-text.ts` (shared with the
 * clipboard/share/export surfaces since ADR-177); this module only adds the
 * single-line collapse and the character budget toasts need.
 *
 * XSS note: this produces TEXT rendered as escaped React children. It is a
 * legibility helper, never a sanitizer — nothing here may be fed to
 * `dangerouslySetInnerHTML`.
 */

import { htmlToPlainText, looksLikeHtml } from './html-plain-text';

/** Character budget for a toast description before ellipsizing. */
export const NOTIFICATION_PREVIEW_MAX_LENGTH = 100;

/**
 * Flatten rich content to a single-line plain-text preview.
 *
 * A no-op on Markdown and plain prose, so it is safe to apply to every
 * notification type.
 *
 * @param text - Notification content, possibly HTML.
 * @param maxLength - Character budget; omit to flatten without truncating.
 * @returns Single-line plain text, ellipsized when it exceeds the budget.
 */
export function toPlainPreview(text: string, maxLength?: number): string {
  if (!text) return '';

  const flat = looksLikeHtml(text) ? htmlToPlainText(text) : text;
  const out = flat.replace(/\s+/g, ' ').trim();
  if (maxLength === undefined || out.length <= maxLength) return out;
  return `${out.slice(0, maxLength)}...`;
}
