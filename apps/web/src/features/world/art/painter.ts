import { project } from '../geometry';
import type { Point } from '../types';
export interface Sprite {
  canvas: HTMLCanvasElement;
  anchorX: number;
  anchorY: number;
  width: number;
  height: number;
}
/** Logical allocation bounds are shared with the scene's pixel-picking broad phase. */
export function spriteFrame(w: number, d: number, h: number): Omit<Sprite, 'canvas'> {
  return {
    width: Math.ceil((w + d) * 32 + 40),
    height: Math.ceil((w + d) * 16 + h * 32 + 48),
    anchorX: d * 32 + 20,
    anchorY: h * 32 + 20,
  };
}
export function shade(color: string, amount: number): string {
  const n = Number.parseInt(color.slice(1), 16);
  const channel = (shift: number) =>
    Math.round(Math.min(255, Math.max(0, ((n >> shift) & 255) + amount)))
      .toString(16)
      .padStart(2, '0');
  return '#' + channel(16) + channel(8) + channel(0);
}
/** Original projected box artwork. Only trusted authored colours reach this painter. */
export class Painter {
  readonly canvas = document.createElement('canvas');
  readonly ctx: CanvasRenderingContext2D;
  readonly anchorX: number;
  readonly anchorY: number;
  readonly width: number;
  readonly height: number;
  constructor(w: number, d: number, h: number, ratio = 1.5) {
    const frame = spriteFrame(w, d, h);
    this.width = frame.width;
    this.height = frame.height;
    this.anchorX = frame.anchorX;
    this.anchorY = frame.anchorY;
    this.canvas.width = Math.ceil(this.width * ratio);
    this.canvas.height = Math.ceil(this.height * ratio);
    const ctx = this.canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas unavailable');
    this.ctx = ctx;
    ctx.scale(ratio, ratio);
    ctx.translate(this.anchorX, this.anchorY);
    ctx.lineJoin = 'round';
  }
  polygon(points: Point[], fill: string | CanvasGradient, stroke?: string): void {
    const c = this.ctx;
    c.beginPath();
    points.forEach((p, i) => (i ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y)));
    c.closePath();
    c.fillStyle = fill;
    c.fill();
    if (stroke) {
      c.strokeStyle = stroke;
      c.lineWidth = 0.65;
      c.stroke();
    }
  }
  private face(points: Point[], color: string, light: number): void {
    const gradient = this.ctx.createLinearGradient(
      Math.min(...points.map(point => point.x)),
      Math.min(...points.map(point => point.y)),
      Math.max(...points.map(point => point.x)),
      Math.max(...points.map(point => point.y))
    );
    gradient.addColorStop(0, shade(color, light + 8));
    gradient.addColorStop(1, shade(color, light - 7));
    this.polygon(points, gradient);
  }
  box(x: number, y: number, z: number, w: number, d: number, h: number, color: string): void {
    const p = (a: number, b: number, c: number) => project({ x: a, y: b }, c);
    this.face(
      [p(x, y + d, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x, y + d, z + h)],
      color,
      -9
    );
    this.face(
      [p(x + w, y, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x + w, y, z + h)],
      color,
      -32
    );
    const top = [p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)];
    this.face(top, color, 13);
    if (h < 0.05 || w < 0.08 || d < 0.08) return;
    const c = this.ctx;
    c.save();
    c.strokeStyle = shade(color, 38);
    c.globalAlpha = 0.43;
    c.lineWidth = 0.75;
    c.beginPath();
    c.moveTo(top[3].x, top[3].y);
    c.lineTo(top[0].x, top[0].y);
    c.lineTo(top[1].x, top[1].y);
    c.stroke();
    c.strokeStyle = shade(color, -45);
    c.globalAlpha = 0.24;
    c.beginPath();
    c.moveTo(top[2].x, top[2].y);
    const foot = p(x + w, y + d, z);
    c.lineTo(foot.x, foot.y);
    c.stroke();
    c.restore();
  }
  /** Horizontal authored detail; avoids a three-face box for a flat mark. */
  surface(x: number, y: number, z: number, w: number, d: number, color: string): void {
    this.polygon(
      [
        project({ x, y }, z),
        project({ x: x + w, y }, z),
        project({ x: x + w, y: y + d }, z),
        project({ x, y: y + d }, z),
      ],
      color
    );
  }
  panel(x: number, y: number, z: number, w: number, h: number, color: string, side = false): void {
    const p = (a: number, b: number, c: number) => project({ x: a, y: b }, c);
    this.polygon(
      side
        ? [p(x, y, z), p(x, y + w, z), p(x, y + w, z + h), p(x, y, z + h)]
        : [p(x, y, z), p(x + w, y, z), p(x + w, y, z + h), p(x, y, z + h)],
      color
    );
  }
  shadow(w: number, d: number): void {
    const p = project({ x: w / 2, y: d / 2 });
    const c = this.ctx;
    c.save();
    c.translate(p.x, p.y + 3);
    c.scale(1, 0.45);
    const radius = (w + d) * 15;
    const gradient = c.createRadialGradient(0, 0, 0, 0, 0, radius);
    gradient.addColorStop(0, 'rgba(20,38,34,.34)');
    gradient.addColorStop(0.38, 'rgba(20,38,34,.16)');
    gradient.addColorStop(1, 'rgba(20,43,38,0)');
    c.fillStyle = gradient;
    c.beginPath();
    c.ellipse(0, 0, radius, radius * 0.7, 0, 0, Math.PI * 2);
    c.fill();
    c.restore();
  }
  sprite(): Sprite {
    return {
      canvas: this.canvas,
      anchorX: this.anchorX,
      anchorY: this.anchorY,
      width: this.width,
      height: this.height,
    };
  }
}
