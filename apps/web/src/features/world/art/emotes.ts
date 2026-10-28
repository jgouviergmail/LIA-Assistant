import type { VisualEmote } from '../emote-timeline';
import { EMOTE_SECONDS, EMOTE_SYMBOLS } from '../emote-catalogue';
import type { Point } from '../types';

/** Clearance between the name plate and a gesture at the top of its lift. */
const PLATE_GAP = 3;
const LIFT = 5;
/**
 * A contact-preserving symbol beside the head, inside the existing actor/occlusion layer.
 * It starts below the name plate's lower edge, so it never covers the name it belongs to.
 */
export function paintEmote(
  c: CanvasRenderingContext2D,
  at: Point,
  event: VisualEmote | null | undefined,
  time: number,
  reduced: boolean,
  plateBottom: number
): void {
  if (!event || time >= event.until || time < event.started) return;
  const phase = Math.min(1, Math.max(0, (time - event.started) / EMOTE_SECONDS));
  const lift = reduced ? 0 : Math.sin(Math.PI * phase) * LIFT;
  const top = plateBottom + PLATE_GAP + LIFT - lift;
  c.save();
  c.globalAlpha = reduced ? 1 : Math.min(1, phase * 8, (1 - phase) * 8);
  c.fillStyle = '#fffdf5';
  c.strokeStyle = '#295953';
  c.lineWidth = 1.5;
  c.beginPath();
  c.roundRect(at.x + 23, top, 34, 30, 10);
  c.fill();
  c.stroke();
  c.font = '20px system-ui, sans-serif';
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  c.fillText(EMOTE_SYMBOLS[event.kind], at.x + 40, top + 16);
  c.restore();
}
