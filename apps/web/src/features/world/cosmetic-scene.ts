import { project, worldToScreen } from './geometry';
import { ambientLifeAt, catAt, type AmbientAgent } from './world-life';
import { CosmeticEffects, type CosmeticFrame } from './cosmetic-effects';
import { cosmeticPropTarget, type CosmeticTarget } from './cosmetic-interactions';
import { reactionAmount } from './art/reactive-decor';
import {
  nextScreen,
  NO_DECOR,
  pressLift,
  pressReach,
  type DecorPresentation,
} from './decor-presentation';
import type { Atmosphere } from './atmosphere';
import { nightStrength } from './art/lighting';
import type { Camera, Point, Quality, WorldDefinition, WorldProp } from './types';
import { projectPhotoDecor, type PhotoDecor } from './photo-decor';

function inView(target: CosmeticTarget, camera: Camera): boolean {
  const screen = worldToScreen(target.point, camera);
  screen.y -= target.elevation * 32 * camera.zoom;
  return screen.x >= 0 && screen.x <= camera.width && screen.y >= 0 && screen.y <= camera.height;
}
/** Owner-local presentation; never writes the simulation or authored world. */
export class CosmeticScene {
  readonly effects = new CosmeticEffects();
  private readonly staticById: ReadonlyMap<string, CosmeticTarget>;
  private near = new Set<string>();
  private nextApproach = 0;
  private decor = new Map<string, DecorPresentation>();
  private naturalLights = false;
  readonly light = (id: string): boolean | undefined => this.decor.get(id)?.light;
  hasLight(): boolean {
    for (const value of this.decor.values()) if (value.light === true) return true;
    return false;
  }
  life: readonly AmbientAgent[] = [];
  cat: WorldProp | null = null;
  frames: ReadonlyMap<string, CosmeticFrame> = new Map();
  constructor(
    private world: WorldDefinition,
    decor: readonly PhotoDecor[] = []
  ) {
    for (const value of projectPhotoDecor(decor)) this.decor.set(value.id, value);
    this.staticById = new Map(
      world.props.flatMap(prop => {
        const target = cosmeticPropTarget(prop);
        return target ? [[target.id, target] as const] : [];
      })
    );
  }
  photoDecor(): readonly PhotoDecor[] {
    return projectPhotoDecor([...this.decor].map(([id, value]) => ({ id, ...value })));
  }
  target(id: string): CosmeticTarget | null {
    const prop = this.staticById.get(id);
    if (prop) return prop;
    if (this.cat?.id === id) return cosmeticPropTarget(this.cat);
    return this.life.find(target => target.id === id && target.action !== 'bird') ?? null;
  }
  cancel(id: string): void {
    this.effects.cancel(id);
    const frames = new Map(this.frames);
    frames.delete(id);
    this.frames = frames;
  }
  presentation(id: string, reduced: boolean): DecorPresentation {
    const value = this.decor.get(id) ?? NO_DECOR;
    const frame = this.frames.get(id);
    if (frame?.action === 'machine')
      return { ...value, machine: reduced ? 0.5 : Math.round(frame.phase * 24) / 24 };
    if (frame?.action === 'workout')
      return {
        ...value,
        press: reduced ? 0.5 : Math.round(pressLift(frame.phase) * 16) / 16,
        barReach: reduced ? 1 : Math.round(pressReach(frame.phase) * 16) / 16,
      };
    return value;
  }
  sample(
    time: number,
    atmosphere: Atmosphere,
    quality: Quality,
    reduced: boolean,
    now: number,
    camera: Camera,
    player: Point
  ): void {
    this.naturalLights = nightStrength(atmosphere.phase) > 0;
    this.cat = catAt(this.world, reduced ? 0 : time);
    this.life = ambientLifeAt(this.world, atmosphere, time, quality, reduced);
    if (now >= this.nextApproach) {
      this.nextApproach = now + 250;
      const near = new Set<string>();
      for (const agent of this.life) {
        if (
          Math.hypot(agent.point.x - player.x, agent.point.y - player.y) > 1.6 ||
          !inView(agent, camera)
        )
          continue;
        near.add(agent.id);
        if (!this.near.has(agent.id)) this.effects.activate(agent, now, true, quality);
      }
      this.near = near;
    }
    const cat = this.cat && cosmeticPropTarget(this.cat);
    const current = new Map(
      [...(cat ? [cat] : []), ...this.life].map(target => [target.id, target])
    );
    this.frames = new Map(
      this.effects.frames(now, quality).flatMap(frame => {
        const target = current.get(frame.id) ?? this.staticById.get(frame.id);
        return target && inView(target, camera) ? [[frame.id, { ...frame, ...target }]] : [];
      })
    );
    this.turnCat(reduced);
  }
  private turnCat(reduced: boolean): void {
    const cat = this.cat;
    const phase = this.frames.get('ambient-cat')?.phase;
    if (!cat || reduced || phase === undefined || phase < 0.1 || phase > 0.75) return;
    const next = ([1, 2, 3, 0] as const)[cat.facing ?? 0];
    this.cat = {
      ...cat,
      facing: next,
      width: cat.depth,
      depth: cat.width,
      x: cat.x + (cat.width - cat.depth) / 2,
      y: cat.y + (cat.depth - cat.width) / 2,
    };
  }
  activate(id: string, camera: Camera, now: number, quality: Quality, origin?: Point): boolean {
    const target = this.target(id);
    if (!target || !inView(target, camera)) return false;
    const previous = this.decor.get(id) ?? NO_DECOR;
    if (target.action === 'lamp') {
      this.decor.set(id, { light: !(previous.light ?? this.naturalLights) });
      return true;
    }
    if (target.action === 'screen') {
      this.decor.set(id, { screen: nextScreen(previous.screen ?? 0) });
      return true;
    }
    return this.effects.activate(
      { ...target, origin: origin ? { ...origin } : undefined },
      now,
      true,
      quality
    );
  }
  pickLife(pixel: Point): string | null {
    for (const agent of [...this.life].reverse()) {
      if (agent.action === 'bird') continue;
      const at = project(agent.point, agent.elevation);
      const beat = this.frames.get(agent.id);
      if (beat) {
        const amount = Math.sin(beat.phase * Math.PI);
        at.x += agent.action === 'butterfly' ? amount * 15 : 0;
        at.y -= amount * (agent.action === 'butterfly' ? 4 : 9);
      }
      if (Math.abs(pixel.x - at.x) <= 8 && Math.abs(pixel.y - at.y) <= 6) return agent.id;
    }
    return null;
  }
  reaction(id: string, reduced: boolean): number {
    const frame = this.frames.get(id);
    if (!frame || frame.action !== 'plant') return 0;
    return reduced ? 0 : Math.round(reactionAmount(frame.phase) * 8) / 8;
  }
  clear(): void {
    this.naturalLights = false;
    this.decor.clear();
    this.effects.clear();
    this.frames = new Map();
    this.near.clear();
    this.life = [];
    this.cat = null;
  }
}
