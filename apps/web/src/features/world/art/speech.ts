/** Screen-sized, cached text layout; no React work in the animation loop. */
import { project } from '../geometry';
import type { Camera, Actor, Point, Rect, Size } from '../types';
import type { Simulation } from '../simulation';
import type { SpeechBubble } from '../speech';
import { avatarLabelOffset } from './person-accessories';
import { fitActorLabel } from './labels';

export function speechLines(
  c: { measureText(text: string): { width: number } },
  text: string,
  width: number
): string[] {
  const chars = Array.from(text),
    lines: string[] = [];
  let current = '';
  for (let index = 0; index < chars.length; index++) {
    const char = chars[index],
      candidate = current + char;
    if (char !== '\n' && c.measureText(candidate).width <= width) {
      current = candidate;
      continue;
    }
    const space = current.lastIndexOf(' ');
    const cut = char === '\n' || space < current.length / 2 ? current.length : space;
    lines.push(current.slice(0, cut).trimEnd());
    current = (current.slice(cut) + (char === '\n' ? '' : char)).trimStart();
    if (lines.length === 4) {
      let tail = lines[3];
      while (tail && c.measureText(tail + '…').width > width)
        tail = Array.from(tail).slice(0, -1).join('');
      lines[3] = tail + '…';
      return lines;
    }
  }
  if (current || !lines.length) lines.push(current);
  return lines;
}
export function speechBox(
  anchor: Point,
  width: number,
  height: number,
  size: Size,
  occupied: readonly Rect[]
): Rect | null {
  if (height > size.height - 16) return null;
  const box = {
    x: Math.max(8, Math.min(size.width - width - 8, anchor.x - width / 2)),
    y: Math.max(8, Math.min(size.height - height - 8, anchor.y - height - 12)),
    width,
    height,
  };
  for (let attempt = 0; attempt <= occupied.length; attempt++) {
    const hit = occupied.find(
      other =>
        box.x < other.x + other.width + 8 &&
        box.x + box.width + 8 > other.x &&
        box.y < other.y + other.height + 8 &&
        box.y + box.height + 8 > other.y
    );
    if (!hit) return box;
    box.y = hit.y - height - 8;
    if (box.y < 8) return null;
  }
  return null;
}
function speaker(sim: Simulation, id: string): Actor | undefined {
  if (id === 'lia') return sim.bip;
  if (id === sim.player.publicId) return sim.player;
  return sim.visitors.find(person => person.id === id);
}
interface Card extends Rect {
  anchor: Point;
  line: SpeechBubble;
  lines: readonly string[];
  colour: string;
  shape: Path2D;
}
function speechShape(box: Rect, anchor: Point): Path2D {
  const { x, y, width, height } = box,
    right = x + width,
    bottom = y + height,
    radius = 12;
  const path = new Path2D();
  path.moveTo(x + radius, y);
  path.lineTo(right - radius, y);
  path.quadraticCurveTo(right, y, right, y + radius);
  path.lineTo(right, bottom - radius);
  path.quadraticCurveTo(right, bottom, right - radius, bottom);
  if (anchor.y - 4 > bottom) {
    const base = Math.max(x + 20, Math.min(right - 20, anchor.x));
    path.lineTo(base + 6, bottom);
    path.lineTo(anchor.x, anchor.y - 4);
    path.lineTo(base - 6, bottom);
  }
  path.lineTo(x + radius, bottom);
  path.quadraticCurveTo(x, bottom, x, bottom - radius);
  path.lineTo(x, y + radius);
  path.quadraticCurveTo(x, y, x + radius, y);
  path.closePath();
  return path;
}
function colour(line: SpeechBubble): string {
  return line.kind === 'lia' ? '#256e69' : line.kind === 'public' ? '#246e45' : '#2e628e';
}
export class SpeechPainter {
  private layouts = new Map<string, { text: string; width: number; lines: string[] }>();
  clear(): void {
    this.layouts.clear();
  }
  draw(
    c: CanvasRenderingContext2D,
    camera: Camera,
    sim: Simulation,
    bubbles: readonly SpeechBubble[]
  ): void {
    c.save();
    c.globalAlpha = 1;
    c.globalCompositeOperation = 'source-over';
    c.shadowColor = 'transparent';
    c.shadowBlur = 0;
    c.shadowOffsetX = 0;
    c.shadowOffsetY = 0;
    c.font = '13px system-ui, sans-serif';
    c.textAlign = 'left';
    c.textBaseline = 'top';
    const occupied: Rect[] = [],
      cards: Card[] = [];
    for (const line of [...bubbles].sort((a, b) => b.until - a.until)) {
      const actor = speaker(sim, line.speaker);
      if (!actor) continue;
      const card = this.plan(c, camera, actor, line, occupied);
      if (card) cards.push(card);
    }
    // All connectors precede all cards, so a raised connector never crosses another message.
    for (const card of cards) this.silhouette(c, card);
    for (const card of cards) this.body(c, card);
    c.restore();
  }
  private layout(c: CanvasRenderingContext2D, line: SpeechBubble, width: number): string[] {
    const old = this.layouts.get(line.id);
    if (old && old.text === line.text && old.width === width) return old.lines;
    const lines = speechLines(c, line.text, width);
    if (this.layouts.size >= 16) this.layouts.clear();
    this.layouts.set(line.id, { text: line.text, width, lines });
    return lines;
  }
  private plan(
    c: CanvasRenderingContext2D,
    camera: Camera,
    actor: Actor,
    line: SpeechBubble,
    occupied: Rect[]
  ): Card | null {
    const p = project(actor.position),
      width = Math.min(260, camera.width - 24);
    const x = (p.x - camera.center.x) * camera.zoom + camera.width / 2;
    const y =
      (p.y - camera.center.y - avatarLabelOffset(actor.appearance) - 16) * camera.zoom +
      camera.height / 2;
    if (width < 120 || x < -20 || x > camera.width + 20 || y < 0 || y > camera.height + 16)
      return null;
    const lines = this.layout(c, line, width - 24),
      height = lines.length * 18 + 43;
    const box = speechBox({ x, y }, width, height, camera, occupied);
    if (!box) return null;
    occupied.push(box);
    return {
      ...box,
      anchor: { x, y },
      line,
      lines,
      colour: colour(line),
      shape: speechShape(box, { x, y }),
    };
  }
  private silhouette(c: CanvasRenderingContext2D, card: Card): void {
    c.fillStyle = '#fffcf5';
    c.strokeStyle = card.colour;
    c.lineWidth = 1.5;
    c.shadowColor = 'rgba(12,30,40,.22)';
    c.shadowBlur = 12;
    c.shadowOffsetY = 4;
    c.fill(card.shape);
    c.stroke(card.shape);
    c.shadowColor = 'transparent';
    c.shadowBlur = 0;
    c.shadowOffsetY = 0;
  }
  private body(c: CanvasRenderingContext2D, card: Card): void {
    const { x, y, width, height, line, lines, colour } = card;
    // Repaint card faces after every silhouette: connectors stay behind all text.
    // The same outer path includes the pointer, so no border crosses its opening.
    c.save();
    c.beginPath();
    c.rect(x - 1, y - 1, width + 2, height + 2);
    c.clip();
    c.fillStyle = '#fffcf5';
    c.strokeStyle = colour;
    c.lineWidth = 1.5;
    c.fill(card.shape);
    c.stroke(card.shape);
    c.restore();
    c.fillStyle = colour;
    c.font = '600 11px system-ui, sans-serif';
    c.fillText(
      fitActorLabel(line.label, s => c.measureText(s).width, width - 36),
      x + 12,
      y + 10
    );
    if (line.kind === 'private') this.lock(c, x + width - 20, y + 14);
    c.fillStyle = '#21333e';
    c.font = '13px system-ui, sans-serif';
    lines.forEach((text, i) => c.fillText(text, x + 12, y + 29 + i * 18));
  }
  private lock(c: CanvasRenderingContext2D, x: number, y: number): void {
    c.beginPath();
    c.arc(x, y - 2, 3, Math.PI, 0);
    c.stroke();
    c.strokeRect(x - 4, y - 2, 8, 6);
  }
}
