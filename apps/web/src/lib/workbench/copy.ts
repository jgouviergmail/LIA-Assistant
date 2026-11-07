/**
 * Copies a text (ADR-369, lot 2).
 *
 * An insecure origin, the plain-HTTP address an instance on a local network opens on, has no
 * `navigator.clipboard`: the page's own selection copies there. Where neither answers, an `async`
 * turns that into the refusal its caller says.
 *
 * @param text - What to copy.
 * @throws Error - When nothing took it.
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
    return;
  }
  copyThroughSelection(text);
}

function copyThroughSelection(text: string): void {
  const focused = document.activeElement;
  const area = document.createElement('textarea');
  area.value = text;
  area.readOnly = true;
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.append(area);
  area.select();
  const copied = typeof document.execCommand === 'function' && document.execCommand('copy');
  area.remove();
  if (focused instanceof HTMLElement) focused.focus();
  if (!copied) throw new Error('clipboard_unavailable');
}
