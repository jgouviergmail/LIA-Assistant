/**
 * Printing a message's text (ADR-369, lot 3).
 *
 * The HTML frame has no origin to print from, so what reaches paper is the text
 * view: a hidden frame of this page, its words set as text nodes alone, so nothing a
 * sender wrote is ever read as markup. A print dialog holds the page, so the frame
 * goes on a timer long after it, never on an event a browser may not send.
 */

/** Long past the dialog: a frame removed too early prints a blank page. */
const FRAME_LIFE_MS = 60_000;
const DOCUMENT = '<!doctype html><meta charset="utf-8"><title></title><body></body>';

/**
 * @param title - The subject.
 * @param lines - Who, to whom, when.
 * @param text - The message.
 */
export function printText(title: string, lines: readonly string[], text: string): void {
  const frame = document.createElement('iframe');
  frame.dataset.print = '';
  frame.title = title;
  frame.style.position = 'fixed';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  frame.addEventListener(
    'load',
    () => {
      const page = frame.contentDocument;
      if (!page) return;
      page.title = title;
      const heading = page.createElement('h1');
      heading.textContent = title;
      page.body.append(heading);
      for (const line of lines) {
        const row = page.createElement('p');
        row.textContent = line;
        page.body.append(row);
      }
      const body = page.createElement('pre');
      body.style.whiteSpace = 'pre-wrap';
      body.style.fontFamily = 'inherit';
      body.textContent = text;
      page.body.append(body);
      frame.contentWindow?.print();
      window.setTimeout(() => frame.remove(), FRAME_LIFE_MS);
    },
    { once: true }
  );
  frame.srcdoc = DOCUMENT;
  document.body.append(frame);
}
