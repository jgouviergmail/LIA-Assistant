/** Bounded pointer picking: a stationary cursor is rechecked as actors/camera move. */
import { screenToWorld } from './geometry';
import type { Camera, Point } from './types';
import type { SceneInteractions, SceneHost, SceneTarget } from './scene-interactions';
export interface SceneHover {
  target: SceneTarget;
  point: Point;
}
export class ScenePointer {
  private point: Point | null = null;
  private next = 0;
  prop: string | null = null;
  value: SceneHover | null = null;
  constructor(
    private canvas: HTMLCanvasElement,
    private pick: (world: Point) => SceneTarget | 'self' | null,
    private interactions: SceneInteractions,
    private host?: SceneHost
  ) {}
  move(point: Point | null): void {
    this.point = point;
    if (!point) this.clear();
  }
  clear(): void {
    this.point = null;
    this.value = null;
    this.prop = null;
    this.canvas.style.cursor = '';
  }
  update(now: number, camera: Camera): void {
    if (!this.point || now < this.next) return;
    this.next = now + 100;
    const hit = this.pick(screenToWorld(this.point, camera));
    const target = hit && hit !== 'self' ? this.interactions.resolve(hit) : null;
    this.value = target && this.host?.canOpen(target) ? { target, point: { ...this.point } } : null;
    this.prop = this.value && hit && hit !== 'self' && hit.kind === 'object' ? hit.id : null;
    this.canvas.style.cursor = this.value ? 'pointer' : '';
  }
}
