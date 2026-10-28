import { createEyeRig } from '@/components/eyes/rig/runtime';
import { mouthPath } from '@/components/eyes/rig/face-geometry';
import type { Actor, Point } from '../types';
import { WORLD_ACTING_ACCENT_MS, type WorldActingFrame } from '../world-acting';
import { relative } from '@/components/eyes/rig/choreo';

import layout from '../../../../public/world/bip/v2/layout.json';

/** Authored poses, losslessly repacked; the native rig supplies eyes and mouth. */
export const LIA_FRAMES = layout.frames;

/** One image and the existing native rig, stepped by the world's clock. No timer. */
export class LiaAtlas {
  private image: HTMLImageElement | null;
  private ready = false;
  private disposed = false;
  private time = 0;
  private rig = createEyeRig({ characterId: 'bip', allowSleep: false });
  private mouth = '';
  private mouthShape: Path2D | null = null;
  private poseKey = '';
  private contextKey = '';
  private gazeKey = '';
  private eventKey: string | null = null;
  private visible = true;
  private hasBeat = false;

  setVisible(value: boolean): void {
    if (this.disposed || value === this.visible) return;
    this.visible = value;
    if (!value) this.cancelBeat();
  }
  private cancelBeat(): void {
    this.rig.settle();
    this.hasBeat = false;
  }

  setActing(frame: WorldActingFrame): void {
    if (this.disposed) return;
    const key = JSON.stringify(frame.pose);
    if (key !== this.poseKey) {
      this.poseKey = key;
      this.rig.setPose(frame.pose);
    }
    const context = JSON.stringify(frame.context);
    if (context !== this.contextKey) {
      this.contextKey = context;
      this.rig.setContext(frame.context);
    }
    const gaze = JSON.stringify(frame.gaze);
    if (gaze !== this.gazeKey) {
      this.gazeKey = gaze;
      this.rig.setGaze(frame.gaze);
    }
    this.syncAccent(frame);
    if (!this.visible) this.cancelBeat();
  }
  private syncAccent(frame: WorldActingFrame): void {
    if (!frame.accentAlive && this.hasBeat) this.cancelBeat();
    if (!frame.eventKey || frame.eventKey === this.eventKey) return;
    this.eventKey = frame.eventKey;
    if (!this.visible || !frame.accentAlive) return;
    this.hasBeat = true;
    this.rig.play(
      relative(
        'bodyY',
        [
          [0, 0],
          [95, 0.018],
          [320, -0.07],
          [650, 0],
        ],
        WORLD_ACTING_ACCENT_MS,
        { frequency: 5.5, damping: 1 }
      )
    );
  }

  constructor() {
    const image = new Image();
    this.image = image;
    image.onload = () => {
      this.ready =
        !this.disposed &&
        image.naturalWidth === layout.width &&
        image.naturalHeight === layout.height;
    };
    image.onerror = () => {
      this.ready = false;
    };
    image.src = layout.src;
  }

  get textureBytes(): number {
    return this.ready ? layout.width * layout.height * 4 : 0;
  }

  /** Prepare this independent atlas for a still; do not step the rig. */
  async prepareImage(): Promise<void> {
    const image = this.image;
    if (this.ready || !image || this.disposed || typeof image.decode !== 'function') return;
    try {
      await image.decode();
    } catch {
      return;
    }
    this.ready =
      !this.disposed &&
      image === this.image &&
      image.naturalWidth === layout.width &&
      image.naturalHeight === layout.height;
  }

  draw(
    c: CanvasRenderingContext2D,
    at: Point,
    actor: Actor,
    time: number,
    reduced: boolean
  ): boolean {
    if (!this.ready || !this.image || this.disposed) return false;
    const frame = LIA_FRAMES[actor.facing] ?? LIA_FRAMES[1];
    const scale = 70 / frame.height;
    this.rig.setReducedMotion(reduced);
    this.rig.step(Math.max(0, Math.min(64, (time - this.time) * 1000)));
    this.time = time;
    const values = this.rig.values();
    const bob = actor.walking && !reduced ? Math.sin(actor.phase * 2) * 0.8 : 0;
    c.save();
    c.translate(at.x, at.y + bob + (reduced ? 0 : values.bodyY * 12));
    c.rotate((Math.max(-2.2, Math.min(2.2, values.bodyRoll + values.tilt * 0.12)) * Math.PI) / 180);
    c.translate(-(frame.width * scale) / 2, -70);
    c.scale(scale, scale);
    c.drawImage(
      this.image,
      frame.x,
      frame.y,
      frame.width,
      frame.height,
      0,
      0,
      frame.width,
      frame.height
    );
    if (actor.facing === 0 || actor.facing === 1) this.face(c, actor.facing);
    c.restore();
    return true;
  }

  private face(c: CanvasRenderingContext2D, facing: number): void {
    const values = this.rig.values();
    c.save();
    // Match the actual visor planes of the two front views, in cropped atlas pixels.
    if (facing === 0) c.transform(1, -0.19, 0.04, 1, 91, 124);
    else c.transform(1, 0.19, -0.04, 1, 72, 83);
    c.fillStyle = '#b3f3fa';
    for (const [side, x] of [
      ['L', 30],
      ['R', 133],
    ] as const) {
      const h = Math.max(3, 46 * values[`sy${side}`] * (1 - values[`blink${side}`]));
      c.beginPath();
      c.roundRect(
        x + values.gazeX * 9,
        36 - h / 2 + values.gazeY * 7,
        36 * values[`sx${side}`],
        h,
        12
      );
      c.fill();
    }
    const shape = mouthPath(values);
    if (shape !== this.mouth) {
      this.mouth = shape;
      this.mouthShape = new Path2D(shape);
    }
    c.translate(62, 76);
    c.scale(0.85, 0.6);
    if (this.mouthShape) c.fill(this.mouthShape);
    c.restore();
  }

  destroy(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.ready = false;
    if (this.image) {
      this.image.onload = null;
      this.image.onerror = null;
      this.image.src = '';
      this.image = null;
    }
    this.mouthShape = null;
  }
}
