/** Distinct static shapes stay readable in back views and reduced motion. */
import type { Point } from '../types';
import type { WorldActingState } from '../world-acting';
const MARKS: Partial<Record<WorldActingState, string>> = {
  waiting: '?',
  error: '!',
  prepared: '…',
  success: '✓',
};
export function paintActingMark(
  c: CanvasRenderingContext2D,
  at: Point,
  state: WorldActingState
): void {
  const mark = MARKS[state];
  if (!mark) return;
  c.save();
  c.translate(at.x + 25, at.y - 57);
  c.fillStyle = '#f8f3e8';
  c.strokeStyle = '#315760';
  c.lineWidth = 1.3;
  c.beginPath();
  c.roundRect(-8, -9, 16, 18, 6);
  c.fill();
  c.stroke();
  c.fillStyle = '#234851';
  c.font = '700 12px system-ui, sans-serif';
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  c.fillText(mark, 0, 0);
  c.restore();
}
