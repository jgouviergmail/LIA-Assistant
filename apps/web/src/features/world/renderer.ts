import { floorEdgeBounds, paintFloorCell } from './art/floor-boundary';
import { paintHoverFootprint } from './art/hover';
import { crystalAura, paintCrystalAura } from './art/crystal-aura';
import { paintStars } from './art/stars';
import { SpeechPainter } from './art/speech';
import type { WorldSpeech } from './speech';
import { SpriteCache, freeSprite } from './art/sprite-cache';
import { appearanceSignature } from './avatar-catalogue';
import { avatarLabelOffset } from './art/person-accessories';
import { isSheltered } from './shelter';
import { ambientStrength, nightColour, nightStrength, shadeSprite } from './art/lighting';
import { paintPondMotion } from './art/pond-motion';
import { sortProps } from './prop-sort';
import { WorldPropIndex } from './prop-index';
import { catAt } from './world-life';
import { paintAmbientLife } from './art/ambient-life';
import { paintObjectMotion } from './art/object-motion';
import type { SceneTarget } from './scene-interactions';
import { groundAt } from './definition';
import { project } from './geometry';
import { paintProp, paintActor } from './art/props';
import { paintFloor } from './art/floors';
import { floorVariant, propTextureKey } from './art/prop-style';
import { actorOccluders } from './occlusion';
import type { Sprite } from './art/painter';
import type {
  Actor,
  Camera,
  Ground,
  Point,
  Quality,
  Rect,
  Tone,
  WorldDefinition,
  WorldProp,
} from './types';
import type { Simulation } from './simulation';
import { LiaAtlas } from './art/lia-atlas';
import { fitActorLabel } from './art/labels';
import { skinHomeProps, type HomeSkin } from './home-projection';
import { NEUTRAL_ATMOSPHERE, type Atmosphere } from './atmosphere';
import {
  paintAtmosphere,
  paintGroundShade,
  paintLampGlow,
  paintGroundLights,
} from './art/atmosphere';

interface Chunk {
  sprite: Sprite;
  x: number;
  y: number;
}
const CHUNK = 8;
const RATIO: Record<Quality, number> = { low: 1, balanced: 1.25, high: 1.75 };
function publicTint(alias: string): Tone {
  let seed = 0;
  for (const character of alias) seed = (seed * 31 + (character.codePointAt(0) ?? 0)) >>> 0;
  return (['violet', 'sage', 'clay', 'teal', 'amber'] as const)[seed % 5];
}
function spriteBytes(sprite: Sprite): number {
  return sprite.canvas.width * sprite.canvas.height * 4;
}
export class WorldRenderer {
  private ctx: CanvasRenderingContext2D;
  private speechPainter = new SpeechPainter();
  private actorLayer: HTMLCanvasElement;
  private actorContext: CanvasRenderingContext2D;
  private sprites = new Map<string, Sprite>();
  private actorSprites = new SpriteCache(12 * 1024 * 1024, 96);
  private floorTiles = new Map<string, Sprite>();
  private chunks = new Map<string, Chunk>();
  private floorEdges: Map<string, Rect>;
  private sorted: readonly WorldProp[];
  private propIndex: WorldPropIndex;
  private pondBeds: readonly WorldProp[];
  private privateProps = new Set<string>();
  private homeSignature = '';
  private atmosphere: Atmosphere = NEUTRAL_ATMOSPHERE;
  private quality: Quality;
  private ratio = 1;
  private disposed = false;
  private lia: LiaAtlas | null = null;
  private nameplates = new Map<string, { label: string; width: number }>();
  drawCount = 0;
  reducedMotion = false;
  constructor(
    private canvas: HTMLCanvasElement,
    private world: WorldDefinition,
    quality: Quality,
    private labels: { player: string; bip: string },
    private speech?: WorldSpeech
  ) {
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('Canvas unavailable');
    this.ctx = ctx;
    this.actorLayer = document.createElement('canvas');
    this.actorLayer.width = 320;
    this.actorLayer.height = 320;
    const actorContext = this.actorLayer.getContext('2d');
    if (!actorContext) throw new Error('Canvas unavailable');
    this.actorContext = actorContext;
    this.quality = quality;
    this.sorted = sortProps(world.props);
    this.propIndex = new WorldPropIndex(this.sorted);
    this.floorEdges = floorEdgeBounds(world);
    this.pondBeds = world.props.filter(prop => prop.kind === 'pond');
    this.lia = new LiaAtlas();
  }
  resize(width: number, height: number): void {
    this.ratio = Math.min(window.devicePixelRatio || 1, RATIO[this.quality]);
    this.canvas.width = Math.max(1, Math.round(width * this.ratio));
    this.canvas.height = Math.max(1, Math.round(height * this.ratio));
  }
  setQuality(quality: Quality): void {
    if (quality === this.quality) return;
    this.quality = quality;
    for (const sprite of this.sprites.values()) freeSprite(sprite);
    this.sprites.clear();
    this.actorSprites.clear();
  }
  setHome(skin: HomeSkin | null): void {
    const signature = skin?.palette ?? '';
    if (this.disposed || signature === this.homeSignature) return;
    this.homeSignature = signature;
    for (const [key, sprite] of this.sprites) {
      if (!key.startsWith('private:')) continue;
      freeSprite(sprite);
      this.sprites.delete(key);
    }
    const props = skinHomeProps(this.world, skin);
    this.privateProps = new Set(
      props.filter((prop, index) => prop !== this.world.props[index]).map(prop => prop.id)
    );
    this.sorted = sortProps(props);
    this.propIndex.clear();
    this.propIndex = new WorldPropIndex(this.sorted);
  }
  setAtmosphere(value: Atmosphere): void {
    if (nightStrength(value.phase) !== nightStrength(this.atmosphere.phase)) {
      for (const [key, sprite] of this.sprites) {
        if (!key.includes(':night:')) continue;
        freeSprite(sprite);
        this.sprites.delete(key);
      }
    }
    this.atmosphere = value;
  }
  private propKey(prop: WorldProp, mask = false): string {
    return propTextureKey(prop, this.privateProps.has(prop.id), mask);
  }

  private asset(key: string, factory: () => Sprite): Sprite {
    let sprite = this.sprites.get(key);
    if (!sprite) {
      sprite = factory();
      this.sprites.set(key, sprite);
    }
    return sprite;
  }
  private draw(sprite: Sprite, x: number, y: number, context = this.ctx): void {
    context.drawImage(
      sprite.canvas,
      x - sprite.anchorX,
      y - sprite.anchorY,
      sprite.width,
      sprite.height
    );
    this.drawCount++;
  }
  private floorKind(x: number, y: number): Ground {
    const kind = groundAt(this.world, x, y);
    if (kind !== 'water') return kind;
    // Authored ponds own their curved water surface. Keep the physical water
    // cells for collision, but never bake rectangular blue edges underneath.
    return this.pondBeds.some(
      pond => x >= pond.x && x < pond.x + pond.width && y >= pond.y && y < pond.y + pond.depth
    )
      ? 'grass'
      : kind;
  }
  private floorTile(kind: Ground, variant: number): Sprite {
    const key = kind + variant;
    let tile = this.floorTiles.get(key);
    if (!tile) {
      tile = paintFloor(kind, variant);
      this.floorTiles.set(key, tile);
    }
    return tile;
  }
  private chunk(cx: number, cy: number): Chunk {
    const key = cx + ':' + cy;
    const cached = this.chunks.get(key);
    if (cached) {
      return cached;
    }
    const canvas = document.createElement('canvas');
    canvas.width = CHUNK * 64 + 4;
    canvas.height = CHUNK * 32 + 4;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas unavailable');
    const anchorX = CHUNK * 32 + 2,
      anchorY = 2;
    for (let y = 0; y < CHUNK && cy + y < this.world.height; y++)
      for (let x = 0; x < CHUNK && cx + x < this.world.width; x++) {
        const kind = this.floorKind(cx + x, cy + y);
        const tile = this.floorTile(kind, floorVariant(kind, cx + x, cy + y));
        const p = project({ x, y }),
          edge = this.floorEdges.get(cx + x + ':' + (cy + y));
        const grass = edge
          ? this.floorTile('grass', floorVariant('grass', cx + x, cy + y))
          : undefined;
        paintFloorCell(ctx, tile, { x: p.x + anchorX, y: p.y + anchorY }, edge, grass);
      }
    const result = {
      x: cx,
      y: cy,
      sprite: { canvas, anchorX, anchorY, width: canvas.width, height: canvas.height },
    };
    this.chunks.set(key, result);
    return result;
  }
  private visible(x: number, y: number, width: number, height: number, camera: Camera): boolean {
    const halfW = camera.width / (2 * camera.zoom),
      halfH = camera.height / (2 * camera.zoom);
    return (
      x + width > camera.center.x - halfW &&
      x - width < camera.center.x + halfW &&
      y + 40 > camera.center.y - halfH &&
      y - height < camera.center.y + halfH
    );
  }
  private floors(camera: Camera): void {
    // Retain the viewport's working set. A smaller LRU evicts visible chunks
    // during the same traversal and rebuilds every surface on every frame.
    for (const [key, chunk] of this.chunks) {
      if (this.floorVisible(chunk.x, chunk.y, camera)) continue;
      freeSprite(chunk.sprite);
      this.chunks.delete(key);
    }
    for (let y = 0; y < this.world.height; y += CHUNK)
      for (let x = 0; x < this.world.width; x += CHUNK) {
        if (!this.floorVisible(x, y, camera)) continue;
        const p = project({ x, y });
        const chunk = this.chunk(x, y);
        this.draw(chunk.sprite, p.x, p.y);
      }
  }
  private floorVisible(x: number, y: number, camera: Camera): boolean {
    const p = project({ x, y });
    return this.visible(p.x, p.y + CHUNK * 32, CHUNK * 32 + 2, CHUNK * 32 + 4, camera);
  }
  private prop(prop: WorldProp, camera: Camera, time: number): void {
    const p = project(prop);
    const projectedDepth = (prop.width + prop.depth) * 16;
    if (
      !this.visible(
        p.x,
        p.y + projectedDepth,
        (prop.width + prop.depth) * 32 + 20,
        prop.height * 32 + projectedDepth + 50,
        camera
      )
    )
      return;
    const strength = ambientStrength(
      this.atmosphere.phase,
      isSheltered(this.world, {
        x: prop.x + prop.width / 2,
        y: prop.y + prop.depth / 2,
      })
    );
    const key = this.propKey(prop) + (strength ? ':night:' + strength : '');
    this.draw(
      this.asset(key, () =>
        shadeSprite(paintProp(prop, this.quality === 'high' ? 2 : 1.5), strength)
      ),
      p.x,
      p.y
    );
    if (prop.kind === 'crystal')
      paintCrystalAura(
        this.ctx,
        prop,
        this.asset('fx:crystal-aura', crystalAura),
        time,
        this.reducedMotion
      );
    paintObjectMotion(this.ctx, prop, time, this.reducedMotion, this.atmosphere);
  }
  private actor(
    actor: Actor,
    bip: boolean,
    time: number,
    c: CanvasRenderingContext2D,
    alias?: string
  ): void {
    const p = project(actor.position);
    c.save();
    const lying = actor.pose?.kind === 'lie';
    const contact = project(actor.position, lying ? actor.pose?.elevation : 0);
    c.translate(contact.x, contact.y + (lying ? 0 : 3));
    c.fillStyle = lying ? 'rgba(24,47,44,.12)' : 'rgba(24,47,44,.24)';
    c.beginPath();
    if (lying) c.ellipse(0, 0, 30, 8, -Math.atan(0.5), 0, Math.PI * 2);
    else c.ellipse(0, 0, 17, 5.4, 0, 0, Math.PI * 2);
    c.fill();
    c.restore();
    this.actorBody(actor, bip, time, c, p, alias);
    const strength = ambientStrength(
      this.atmosphere.phase,
      isSheltered(this.world, actor.position)
    );
    if (strength) {
      c.save();
      c.globalCompositeOperation = 'source-atop';
      c.fillStyle = nightColour(strength);
      c.fillRect(p.x - 80, p.y - 112, 160, 160);
      c.restore();
    }
    this.actorLabel(actor, bip, c, p, alias);
  }
  private actorLabel(
    actor: Actor,
    bip: boolean,
    c: CanvasRenderingContext2D,
    p: Point,
    alias?: string
  ): void {
    c.font = '600 12px system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    const full = alias ?? actor.label ?? (bip ? this.labels.bip : this.labels.player);
    let plate = this.nameplates.get(full);
    if (!plate) {
      const label = fitActorLabel(full, text => c.measureText(text).width, 116);
      plate = { label, width: c.measureText(label).width + 18 };
      if (this.nameplates.size >= 32) this.nameplates.clear();
      this.nameplates.set(full, plate);
    }
    const { label, width: w } = plate,
      y = p.y - (bip ? 83 : avatarLabelOffset(actor.appearance));
    c.fillStyle = bip ? '#295953' : '#37434e';
    c.beginPath();
    c.roundRect(p.x - w / 2, y - 10, w, 21, 7);
    c.fill();
    c.fillStyle = '#fffdf5';
    c.fillText(label, p.x, y + 1);
  }
  private actorBody(
    actor: Actor,
    bip: boolean,
    time: number,
    c: CanvasRenderingContext2D,
    p: Point,
    alias?: string
  ): void {
    if (!(bip && this.lia?.draw(c, p, actor, time, this.reducedMotion))) {
      const phase = actor.walking && !this.reducedMotion ? Math.floor(actor.phase) % 8 : 0;
      const tone = publicTint(alias ?? actor.label ?? this.labels.player);
      const heading = bip ? actor.facing : (actor.heading ?? actor.facing * 2);
      const key =
        (bip ? 'bip' : 'person') +
        ':' +
        (actor.appearance ? appearanceSignature(actor.appearance) : 'legacy') +
        ':' +
        tone +
        ':' +
        heading +
        ':' +
        phase +
        ':' +
        (actor.pose ? actor.pose.kind + actor.pose.elevation : 'stand');
      this.draw(
        this.actorSprites.get(key, () =>
          paintActor(
            bip,
            actor.facing,
            phase,
            1.5,
            tone,
            actor.heading,
            actor.pose,
            actor.appearance
          )
        ),
        p.x,
        p.y,
        c
      );
    }
  }
  private actorImage(actor: Actor, bip: boolean, time: number, alias?: string): Rect {
    const p = project(actor.position);
    const area = { x: p.x - 80, y: p.y - 112, width: 160, height: 160 };
    const c = this.actorContext;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = 'source-over';
    c.clearRect(0, 0, 320, 320);
    c.setTransform(2, 0, 0, 2, -area.x * 2, -area.y * 2);
    this.actor(actor, bip, time, c, alias);
    // Erase only solid foreground artwork. Repainting whole props would double
    // blend their shadows and damage pixels outside the actor's silhouette.
    c.globalCompositeOperation = 'destination-out';
    for (const prop of actorOccluders(this.propIndex.query(area), actor.position, area)) {
      if (prop.id === actor.pose?.prop) continue;
      const at = project(prop);
      const key = this.propKey(prop, true);
      this.draw(
        this.asset(key, () => paintProp(prop, this.quality === 'high' ? 2 : 1.5, false)),
        at.x,
        at.y,
        c
      );
    }
    c.globalCompositeOperation = 'source-over';
    return area;
  }
  private compositeActor(
    actor: Actor,
    bip: boolean,
    time: number,
    camera: Camera,
    alias?: string
  ): void {
    const foot = project(actor.position);
    // Include the full 160px actor layer, nameplate and raised/lying poses.
    // Offscreen actors must not rasterize artwork or foreground masks.
    if (!this.visible(foot.x, foot.y + 8, 80, 120, camera)) return;
    const area = this.actorImage(actor, bip, time, alias);
    this.ctx.drawImage(this.actorLayer, area.x, area.y, area.width, area.height);
    this.drawCount++;
  }
  /** Read back a single pixel on a deliberate tap or the bounded hover tick, using the same occlusion as paint. */
  pick(point: Point, sim: Simulation): SceneTarget | 'self' | null {
    const pixel = project(point);
    return this.pickActor(pixel, sim) ?? this.pickProp(pixel);
  }
  private pickActor(pixel: Point, sim: Simulation): SceneTarget | 'self' | null {
    const actors = [
      { actor: sim.player, target: 'self' as const, bip: false, alias: undefined },
      { actor: sim.bip, target: { kind: 'lia' as const }, bip: true, alias: undefined },
      ...sim.visitors.map(actor => ({
        actor,
        target: { kind: 'peer' as const, id: actor.id },
        bip: false,
        alias: actor.label,
      })),
    ]
      .sort(
        (a, b) => a.actor.position.x + a.actor.position.y - b.actor.position.x - b.actor.position.y
      )
      .reverse();
    for (const item of actors) {
      const foot = project(item.actor.position);
      if (Math.abs(pixel.x - foot.x) >= 80 || pixel.y < foot.y - 112 || pixel.y >= foot.y + 48)
        continue;
      const area = this.actorImage(item.actor, item.bip, sim.time, item.alias);
      if (
        this.actorContext.getImageData(
          Math.floor((pixel.x - area.x) * 2),
          Math.floor((pixel.y - area.y) * 2),
          1,
          1
        ).data[3] > 32
      )
        return item.target;
    }
    return null;
  }
  private pickProp(pixel: Point): SceneTarget | null {
    const candidates = this.propIndex.query({ x: pixel.x, y: pixel.y, width: 1, height: 1 });
    for (let index = candidates.length - 1; index >= 0; index--) {
      const prop = candidates[index];
      if (prop.height < 0.1) continue;
      const at = project(prop);
      const x = pixel.x - at.x,
        y = pixel.y - at.y;
      if (
        x < -prop.depth * 32 - 20 ||
        x > prop.width * 32 + 20 ||
        y < -Math.max(prop.height, 2.5) * 32 - 20 ||
        y > (prop.width + prop.depth) * 16 + 28
      )
        continue;
      const sprite = this.asset(this.propKey(prop, true), () =>
        paintProp(prop, this.quality === 'high' ? 2 : 1.5, false)
      );
      const px = Math.floor(((x + sprite.anchorX) * sprite.canvas.width) / sprite.width);
      const py = Math.floor(((y + sprite.anchorY) * sprite.canvas.height) / sprite.height);
      if (px < 0 || py < 0 || px >= sprite.canvas.width || py >= sprite.canvas.height) continue;
      if ((sprite.canvas.getContext('2d')?.getImageData(px, py, 1, 1).data[3] ?? 0) > 32)
        return { kind: 'object', id: prop.id };
    }
    return null;
  }
  render(camera: Camera, sim: Simulation, hovered: string | null = null): void {
    if (this.disposed) return;
    const c = this.ctx;
    this.drawCount = 0;
    c.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    c.fillStyle = '#131d30';
    c.fillRect(0, 0, camera.width, camera.height);
    paintStars(c, camera, this.atmosphere.phase, this.quality);
    const glow = nightStrength(this.atmosphere.phase)
      ? this.asset('ambient:lamp-glow', paintLampGlow)
      : null;
    c.translate(camera.width / 2, camera.height / 2);
    c.scale(camera.zoom, camera.zoom);
    c.translate(-camera.center.x, -camera.center.y);
    this.floors(camera);
    c.save();
    c.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    paintGroundShade(c, this.world, camera, this.atmosphere);
    paintGroundLights(c, this.world, camera, this.atmosphere, glow);
    c.restore();
    this.paintGroundMarkers(sim, hovered);
    const actors = [
      { value: sim.player, bip: false, alias: undefined },
      { value: sim.bip, bip: true, alias: undefined },
      ...sim.visitors.map(visitor => ({ value: visitor, bip: false, alias: visitor.label })),
    ].sort(
      (a, b) => a.value.position.x + a.value.position.y - (b.value.position.x + b.value.position.y)
    );
    for (const prop of this.sorted) if (prop.height < 0.1) this.prop(prop, camera, sim.time);
    paintPondMotion(c, this.world, camera, sim.time, this.quality, this.reducedMotion);
    let cat = catAt(this.world, this.reducedMotion ? 0 : sim.time);
    for (const prop of this.sorted) {
      if (prop.height < 0.1) continue;
      if (
        cat &&
        cat.x + cat.y + cat.width + cat.depth <= prop.x + prop.y + prop.width + prop.depth
      ) {
        this.prop(cat, camera, sim.time);
        cat = null;
      }
      this.prop(prop, camera, sim.time);
    }
    if (cat) this.prop(cat, camera, sim.time);
    paintAmbientLife(c, this.world, this.atmosphere, sim.time, this.quality, this.reducedMotion);
    for (const item of actors)
      this.compositeActor(item.value, item.bip, sim.time, camera, item.alias);
    c.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    paintAtmosphere(
      c,
      this.world,
      camera,
      this.atmosphere,
      sim.time,
      this.quality,
      this.reducedMotion,
      glow
    );
    this.paintSpeech(camera, sim);
  }
  private paintGroundMarkers(sim: Simulation, hovered: string | null): void {
    const c = this.ctx;
    const selected = hovered ? this.sorted.find(prop => prop.id === hovered) : null;
    if (selected) paintHoverFootprint(c, selected);
    const goal = sim.player.path.at(-1);
    if (goal) {
      const p = project(goal);
      c.strokeStyle = '#f4ead0';
      c.lineWidth = 2;
      c.beginPath();
      c.ellipse(p.x, p.y, 13, 6, 0, 0, Math.PI * 2);
      c.stroke();
    }
  }
  private paintSpeech(camera: Camera, sim: Simulation): void {
    if (this.speech) this.speechPainter.draw(this.ctx, camera, sim, this.speech.getSnapshot());
  }
  get textureBytes(): number {
    let result = this.actorLayer.width * this.actorLayer.height * 4;
    for (const sprite of this.sprites.values()) result += spriteBytes(sprite);
    for (const sprite of this.floorTiles.values()) result += spriteBytes(sprite);
    for (const chunk of this.chunks.values()) result += spriteBytes(chunk.sprite);
    result += this.actorSprites.bytes;
    result += this.lia?.textureBytes ?? 0;
    return result;
  }
  destroy(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.lia?.destroy();
    this.lia = null;
    for (const sprite of this.sprites.values()) freeSprite(sprite);
    for (const sprite of this.floorTiles.values()) freeSprite(sprite);
    for (const chunk of this.chunks.values()) freeSprite(chunk.sprite);
    this.sprites.clear();
    this.actorSprites.clear();
    this.floorTiles.clear();
    this.chunks.clear();
    this.floorEdges.clear();
    this.nameplates.clear();
    this.speechPainter.clear();
    this.privateProps.clear();
    this.homeSignature = '';
    this.sorted = [];
    this.propIndex.clear();
    this.actorLayer.width = 0;
    this.actorLayer.height = 0;
    this.canvas.width = 1;
    this.canvas.height = 1;
  }
}
