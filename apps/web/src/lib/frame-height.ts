/**
 * The height a widget frame reports, applied within what the conversation allows.
 *
 * Shared by the skill and page bridges: a frame says how tall it is, and the host
 * bounds it, so a page can neither vanish nor take the whole thread.
 */

const MIN_FRAME_HEIGHT_PX = 80;
const MAX_FRAME_HEIGHT_RATIO = 0.8;

/**
 * Resize a widget iframe to the height its document reports.
 *
 * @param iframe - The frame.
 * @param height - The reported height; anything but a finite number is ignored.
 */
export function applyFrameHeight(iframe: HTMLIFrameElement, height: unknown): void {
  if (typeof height !== 'number' || !Number.isFinite(height)) return;
  const maxHeight = window.innerHeight * MAX_FRAME_HEIGHT_RATIO;
  iframe.style.height = `${Math.max(MIN_FRAME_HEIGHT_PX, Math.min(height, maxHeight))}px`;
  // Release the initial aspect-ratio placeholder so the explicit height takes
  // full effect without fighting the CSS rule.
  iframe.style.aspectRatio = 'auto';
}
