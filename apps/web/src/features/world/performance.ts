import type { WorldMetrics } from './types';
const MAX_SAMPLES = 180;
/** Anchored deadlines retain fractional time across irregular display refreshes. */
export class PaintCadence {
  private next = 0;
  private rate = 0;
  due(now: number, fps: number): boolean {
    if (fps <= 0) {
      this.reset();
      return true;
    }
    if (this.rate !== fps) {
      this.rate = fps;
      this.next = now;
    }
    if (now + 0.25 < this.next) return false;
    const interval = 1000 / fps;
    this.next += (Math.floor(Math.max(0, now - this.next) / interval) + 1) * interval;
    return true;
  }
  reset(): void {
    this.next = this.rate = 0;
  }
}
/** Measures actual frame intervals separately from work done inside a render. */
export class FrameMeter {
  private frames: number[] = [];
  private renders: number[] = [];
  add(interval: number, render: number): void {
    if (!Number.isFinite(interval + render) || interval <= 0 || interval > 10_000 || render < 0)
      return;
    this.frames.push(interval);
    this.renders.push(render);
    if (this.frames.length > MAX_SAMPLES) {
      this.frames.shift();
      this.renders.shift();
    }
  }
  read(sprites: number, textureBytes: number): WorldMetrics {
    const percentile = (values: number[]) =>
      [...values].sort((a, b) => a - b)[Math.max(0, Math.ceil(values.length * 0.95) - 1)] ?? 0;
    const average = this.frames.reduce((a, b) => a + b, 0) / this.frames.length;
    return {
      fps: average ? 1000 / average : 0,
      frameP95: percentile(this.frames),
      renderP95: percentile(this.renders),
      sprites,
      textureBytes,
    };
  }
  reset(): void {
    this.frames = [];
    this.renders = [];
  }
}
