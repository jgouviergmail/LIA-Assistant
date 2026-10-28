/** Shared dock width and camera projection; neither changes spatial authority. */
export const WORLD_CONVERSATION_WIDTH = 576;
export function conversationFocusOffset(width: number, zoom: number, open: boolean): number {
  if (!open || width < 768 || !Number.isFinite(width + zoom) || zoom <= 0) return 0;
  const offset = WORLD_CONVERSATION_WIDTH / (2 * zoom);
  return Number.isFinite(offset) ? offset : 0;
}
