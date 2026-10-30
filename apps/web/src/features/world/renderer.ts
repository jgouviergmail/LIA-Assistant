import { floorEdgeBounds, paintFloorCell } from './art/floor-boundary';
import { paintHoverFootprint } from './art/hover';
import type { Season } from './season';
import { SEASONAL_KINDS } from './art/seasonal-palette';
import { paintRoute } from './route-presentation';
import { hitsPrivateSignal, paintPrivateSignal } from './art/private-signals';
import type { PrivateSignalPresentation } from './private-signal-projection';
import { NEUTRAL_WORLD_ACTING, type WorldActingFrame } from './world-acting';
import { paintActingMark } from './art/acting-mark';
import { crystalAura, paintCrystalAura } from './art/crystal-aura';
import { paintStars } from './art/stars';
import { SpeechPainter } from './art/speech';
import type { WorldSpeech } from './speech';
import { SpriteCache, freeSprite } from './art/sprite-cache';
import { paintPathVerge } from './art/terrain-edge';
import { appearanceSignature } from './avatar-catalogue';
import { avatarLabelOffset } from './art/person-accessories';
import { isSheltered } from './shelter';
import { ambientStrength, nightColour, nightStrength, shadeSprite } from './art/lighting';
import { paintPondMotion } from './art/pond-motion';
import { sortProps } from './prop-sort';
import { WorldPropIndex, hasPickSurface } from './prop-index';
import { CosmeticScene } from './cosmetic-scene';
import {
  decorSignature,
  NO_DECOR,
  NO_DECOR_SIGNATURE,
  type DecorPresentation,
} from './decor-presentation';
import { cosmeticActor } from './art/cosmetic-actor';
import { heldBarbellOffset, paintHeldBarbell } from './art/barbell';
import type { PhotoDecor } from './photo-decor';
import { paintCosmeticResponse } from './art/reactive-decor';
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
import { paintEmote } from './art/emotes';
import { projectPhotoScene } from './photo-projection';
import { preparePhotoAsset } from './photo-assets';
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
/** A bench under a lift draws no bar of its own: the held bar is drawn with the body. */
const LIFTING: DecorPresentation = Object.freeze({ press: 0 });
export class WorldRenderer {
  private cosmetics: CosmeticScene;
  private ownActor: Actor | null = null;
  private reactiveSprites = new SpriteCache(3 * 1024 * 1024, 48);
  /** Static texture identity per authored prop object; dropped with the season or home skin. */
  private propKeys = new WeakMap<WorldProp, [color?: string, mask?: string]>();
  cosmeticTarget(id: string) {
    return this.disposed ? null : this.cosmetics.target(id);
  }
  cancelCosmetic(id: string): void {
    this.cosmetics.cancel(id);
  }
  activateCosmetic(id: string, camera: Camera, sim: Simulation): boolean {
    return (
      !this.disposed &&
      this.cosmetics.activate(id, camera, performance.now(), this.quality, sim.player.position)
    );
  }
  get activeCosmeticEffects(): number {
    return this.cosmetics.frames.size;
  }
  private season: Season = 'neutral';
  setSeason(value: Season): void {
    if (this.disposed || value === this.season) return;
    this.season = value;
    this.propKeys = new WeakMap();
    this.reactiveSprites.clear();
    for (const [key, sprite] of this.sprites) {
      if (!key.startsWith('season:')) continue;
      freeSprite(sprite);
      this.sprites.delete(key);
    }
  }
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
  private homeSkin: HomeSkin | null = null;
  private atmosphere: Atmosphere = NEUTRAL_ATMOSPHERE;
  private quality: Quality;
  private ratio = 1;
  private disposed = false;
  private lia: LiaAtlas | null = null;
  private nameplates = new Map<string, { label: string; width: number }>();
  drawCount = 0;
  reducedMotion = false;
  showRoute = true;
  private acting: WorldActingFrame = NEUTRAL_WORLD_ACTING;
  private actingDirty = false;
  setActing(frame: WorldActingFrame): void {
    if (this.disposed) return;
    this.acting = frame;
    this.actingDirty = true;
  }
  private signals = new Map<string, PrivateSignalPresentation>();
  setPrivateSignals(signals: readonly PrivateSignalPresentation[]): void {
    if (this.disposed) return;
    this.signals = new Map(signals.slice(0, 32).map(signal => [signal.propId, signal]));
  }
  constructor(
    private canvas: HTMLCanvasElement,
    private world: WorldDefinition,
    quality: Quality,
    private labels: { player: string; bip: string },
    private speech?: WorldSpeech,
    private purpose: 'interactive' | 'photo' = 'interactive',
    decor: readonly PhotoDecor[] = []
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
    this.cosmetics = new CosmeticScene(world, decor);
    this.sorted = sortProps(world.props);
    this.propIndex = new WorldPropIndex(this.sorted);
    this.floorEdges = floorEdgeBounds(world);
    this.pondBeds = world.props.filter(prop => prop.kind === 'pond');
    this.lia = new LiaAtlas();
  }
  resize(width: number, height: number): void {
    // A photo is exactly the requested pixels, whatever the screen density.
    this.ratio =
      this.purpose === 'photo' ? 1 : Math.min(window.devicePixelRatio || 1, RATIO[this.quality]);
    this.canvas.width = Math.max(1, Math.round(width * this.ratio));
    this.canvas.height = Math.max(1, Math.round(height * this.ratio));
  }
  setQuality(quality: Quality): void {
    if (quality === this.quality) return;
    this.quality = quality;
    for (const sprite of this.sprites.values()) freeSprite(sprite);
    this.sprites.clear();
    this.actorSprites.clear();
    this.reactiveSprites.clear();
  }
  setHome(skin: HomeSkin | null): void {
    const signature = skin?.palette ?? '';
    if (this.disposed || signature === this.homeSignature) return;
    this.homeSignature = signature;
    this.homeSkin = skin ? { palette: skin.palette } : null;
    this.propKeys = new WeakMap();
    this.reactiveSprites.clear();
    for (const [key, sprite] of this.sprites) {
      if (!key.startsWith('private:') && !key.includes(':private:')) continue;
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
  photoScene(sim: Simulation, camera: Camera) {
    return this.disposed
      ? null
      : projectPhotoScene({
          player: sim.player,
          bip: sim.bip,
          camera,
          time: sim.time,
          season: this.season,
          atmosphere: this.atmosphere,
          home: this.homeSkin,
          decor: this.cosmetics.photoDecor(),
        });
  }
  preparePhoto(signal: AbortSignal): Promise<void> {
    return preparePhotoAsset(this.lia?.prepareImage(), signal);
  }
  setAtmosphere(value: Atmosphere): void {
    if (value.phase !== this.atmosphere.phase) {
      for (const [key, sprite] of this.sprites) {
        if (!key.includes(':night:')) continue;
        freeSprite(sprite);
        this.sprites.delete(key);
      }
    }
    this.atmosphere = value;
  }
  private propKey(prop: WorldProp, mask = false): string {
    let keys = this.propKeys.get(prop);
    if (!keys) this.propKeys.set(prop, (keys = []));
    const slot = mask ? 1 : 0;
    return (keys[slot] ??= this.composePropKey(prop, mask));
  }
  private composePropKey(prop: WorldProp, mask: boolean): string {
    const base = propTextureKey(prop, this.privateProps.has(prop.id), mask);
    return SEASONAL_KINDS.has(prop.kind) ? 'season:' + this.propSeason(prop) + ':' + base : base;
  }
  private propSeason(prop: WorldProp): Season {
    const foliage = prop.kind === 'plant' || prop.kind === 'planter';
    return foliage &&
      isSheltered(this.world, { x: prop.x + prop.width / 2, y: prop.y + prop.depth / 2 })
      ? 'neutral'
      : this.season;
  }
  private propSprite(prop: WorldProp, mask = false, strength = 0): Sprite {
    const reaction = this.cosmetics.reaction(prop.id, this.reducedMotion);
    const presentation = this.cosmetics.presentation(prop.id, this.reducedMotion);
    const decor =
      prop.kind === 'weightbench' && presentation.press !== undefined ? LIFTING : presentation;
    const key =
      this.propKey(prop, mask) +
      (strength ? ':night:' + this.atmosphere.phase + ':' + strength : '') +
      ':' +
      (decor === NO_DECOR ? NO_DECOR_SIGNATURE : decorSignature(decor));
    const paint = () =>
      shadeSprite(
        paintProp(
          prop,
          this.quality === 'high' ? 2 : 1.5,
          !mask,
          this.propSeason(prop),
          reaction,
          decor
        ),
        strength,
        this.atmosphere.phase
      );
    return reaction || Object.keys(decor).length
      ? this.reactiveSprites.get(key + ':reaction:' + reaction, paint)
      : this.asset(key, paint);
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
        if (kind === 'path')
          paintPathVerge(ctx, this.world, cx + x, cy + y, { x: p.x + anchorX, y: p.y + anchorY });
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
    this.draw(this.propSprite(prop, false, strength), p.x, p.y);
    if (prop.kind === 'crystal')
      paintCrystalAura(
        this.ctx,
        prop,
        this.asset('fx:crystal-aura', crystalAura),
        time,
        this.reducedMotion
      );
    const reaction = this.cosmetics.frames.get(prop.id);
    paintObjectMotion(
      this.ctx,
      prop,
      time,
      this.reducedMotion,
      this.atmosphere,
      reaction,
      this.propSeason(prop)
    );
    if (reaction) paintCosmeticResponse(this.ctx, reaction, this.reducedMotion);
    const signal = this.signals.get(prop.id);
    if (signal) paintPrivateSignal(this.ctx, prop, signal);
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
    if (bip && this.purpose === 'interactive') paintActingMark(c, p, this.acting.state);
    const strength = ambientStrength(
      this.atmosphere.phase,
      isSheltered(this.world, actor.position)
    );
    if (strength) {
      c.save();
      c.globalCompositeOperation = 'source-atop';
      c.fillStyle = nightColour(strength, this.atmosphere.phase);
      c.fillRect(p.x - 80, p.y - 112, 160, 160);
      c.restore();
    }
    if (this.purpose === 'photo') return;
    const plateBottom = this.actorLabel(actor, bip, c, p, alias);
    if (!bip)
      paintEmote(c, p, actor.emote, performance.now() / 1000, this.reducedMotion, plateBottom);
  }
  /** Paints the name plate and returns its lower edge, which a gesture must never cover. */
  private actorLabel(
    actor: Actor,
    bip: boolean,
    c: CanvasRenderingContext2D,
    p: Point,
    alias?: string
  ): number {
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
    const lying = actor.pose?.kind === 'lie';
    const { label, width: w } = plate,
      y = p.y - (lying ? 104 : bip ? 83 : avatarLabelOffset(actor.appearance));
    c.fillStyle = bip ? '#295953' : '#37434e';
    c.beginPath();
    c.roundRect(p.x - w / 2, y - (lying ? 8 : 10), w, lying ? 16 : 21, 7);
    c.fill();
    c.fillStyle = '#fffdf5';
    c.fillText(label, p.x, y + 1);
    return y + (lying ? 8 : 11);
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
      const { heading, interaction } =
        actor === this.ownActor
          ? cosmeticActor(actor, this.cosmetics.frames, this.reducedMotion)
          : {
              heading: bip ? actor.facing : (actor.heading ?? actor.facing * 2),
              interaction: undefined,
            };
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
        (actor.pose ? actor.pose.kind + actor.pose.elevation : 'stand') +
        ':' +
        JSON.stringify(interaction);
      this.draw(
        this.actorSprites.get(key, () =>
          paintActor(
            bip,
            actor.facing,
            phase,
            1.5,
            tone,
            heading,
            actor.pose,
            actor.appearance,
            interaction
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
    this.heldBarbell(actor, c);
    // Erase only solid foreground artwork. Repainting whole props would double
    // blend their shadows and damage pixels outside the actor's silhouette.
    c.globalCompositeOperation = 'destination-out';
    for (const prop of actorOccluders(this.propIndex.query(area), actor.position, area)) {
      if (prop.id === actor.pose?.prop) continue;
      const at = project(prop);
      this.draw(this.propSprite(prop, true), at.x, at.y, c);
    }
    c.globalCompositeOperation = 'source-over';
    return area;
  }
  private heldBarbell(actor: Actor, c: CanvasRenderingContext2D): void {
    if (actor !== this.ownActor || !actor.pose) return;
    const frame = this.cosmetics.frames.get(actor.pose.prop);
    if (frame?.action !== 'workout') return;
    const prop = this.world.props.find(item => item.id === frame.id);
    if (!prop) return;
    const decor = this.cosmetics.presentation(prop.id, this.reducedMotion);
    const strength = ambientStrength(
      this.atmosphere.phase,
      isSheltered(this.world, actor.position)
    );
    // The bar is rigid and the projection linear: one sprite per bench and light,
    // moved along its lift, never one sprite per quantised press position.
    const sprite = this.asset(
      'held:' +
        this.propKey(prop) +
        (strength ? ':night:' + this.atmosphere.phase + ':' + strength : ''),
      () =>
        shadeSprite(
          paintHeldBarbell(prop, this.quality === 'high' ? 2 : 1.5),
          strength,
          this.atmosphere.phase
        )
    );
    const at = project(prop);
    const lift = heldBarbellOffset(prop, decor);
    this.draw(sprite, at.x + lift.x, at.y + lift.y, c);
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
    const actor = this.pickActor(pixel, sim);
    if (actor) return actor;
    const life = this.cosmetics.pickLife(pixel);
    return life ? { kind: 'object', id: life } : this.pickProp(pixel);
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
    // The index retains the complete scene order, including wall dependencies
    // outside this pixel's candidates. Insert the moving cat as render() does.
    const candidates = this.propIndex.query({ x: pixel.x, y: pixel.y, width: 1, height: 1 }),
      cat = this.cosmetics.cat;
    if (cat) {
      const index = candidates.findIndex(
        prop => cat.x + cat.y + cat.width + cat.depth <= prop.x + prop.y + prop.width + prop.depth
      );
      candidates.splice(index < 0 ? candidates.length : index, 0, cat);
    }
    for (let index = candidates.length - 1; index >= 0; index--) {
      const prop = candidates[index];
      if (hasPickSurface(prop) && this.hitsProp(prop, pixel))
        return { kind: 'object', id: prop.id };
    }
    return null;
  }
  private hitsProp(prop: WorldProp, pixel: Point): boolean {
    if (this.signals.has(prop.id) && hitsPrivateSignal(prop, pixel)) return true;
    const at = project(prop);
    const x = pixel.x - at.x,
      y = pixel.y - at.y;
    if (
      x < -prop.depth * 32 - 20 ||
      x > prop.width * 32 + 20 ||
      y < -Math.max(prop.height, 2.5) * 32 - 20 ||
      y > (prop.width + prop.depth) * 16 + 28
    )
      return false;
    const sprite = this.propSprite(prop, true);
    const px = Math.floor(((x + sprite.anchorX) * sprite.canvas.width) / sprite.width);
    const py = Math.floor(((y + sprite.anchorY) * sprite.canvas.height) / sprite.height);
    if (px < 0 || py < 0 || px >= sprite.canvas.width || py >= sprite.canvas.height) return false;
    return (sprite.canvas.getContext('2d')?.getImageData(px, py, 1, 1).data[3] ?? 0) > 32;
  }
  private syncActing(camera: Camera, sim: Simulation): void {
    if (!this.lia) return;
    const foot = project(sim.bip.position);
    this.lia.setVisible(this.visible(foot.x, foot.y + 8, 80, 120, camera));
    if (!this.actingDirty) return;
    this.lia.setActing(this.acting);
    this.actingDirty = false;
  }
  render(camera: Camera, sim: Simulation, hovered: string | null = null): void {
    if (this.disposed) return;
    this.ownActor = sim.player;
    this.cosmetics.sample(
      sim.time,
      this.atmosphere,
      this.quality,
      this.reducedMotion,
      performance.now(),
      camera,
      sim.player.position
    );
    this.syncActing(camera, sim);
    const c = this.ctx;
    this.drawCount = 0;
    c.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    c.fillStyle = '#131d30';
    c.fillRect(0, 0, camera.width, camera.height);
    paintStars(c, camera, this.atmosphere.phase, this.quality);
    const glow =
      nightStrength(this.atmosphere.phase) || this.cosmetics.hasLight()
        ? this.asset('ambient:lamp-glow', paintLampGlow)
        : null;
    c.translate(camera.width / 2, camera.height / 2);
    c.scale(camera.zoom, camera.zoom);
    c.translate(-camera.center.x, -camera.center.y);
    this.floors(camera);
    c.save();
    c.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    paintGroundShade(c, this.world, camera, this.atmosphere);
    paintGroundLights(c, this.world, camera, this.atmosphere, glow, this.cosmetics.light);
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
    let cat = this.cosmetics.cat;
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
    paintAmbientLife(
      c,
      this.world,
      this.atmosphere,
      sim.time,
      this.quality,
      this.reducedMotion,
      this.cosmetics.life,
      this.cosmetics.frames
    );
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
      glow,
      this.cosmetics.light
    );
    this.paintSpeech(camera, sim);
  }
  private paintGroundMarkers(sim: Simulation, hovered: string | null): void {
    if (this.purpose === 'photo') return;
    const c = this.ctx;
    paintRoute(c, sim.player.position, sim.player.path, this.showRoute);
    const selected = hovered ? this.sorted.find(prop => prop.id === hovered) : null;
    if (selected) paintHoverFootprint(c, selected);
    const goal = sim.player.path.at(-1);
    if (goal && this.showRoute) {
      const p = project(goal);
      c.strokeStyle = '#f4ead0';
      c.lineWidth = 2;
      c.beginPath();
      c.ellipse(p.x, p.y, 13, 6, 0, 0, Math.PI * 2);
      c.stroke();
    }
  }
  private paintSpeech(camera: Camera, sim: Simulation): void {
    if (this.purpose === 'interactive' && this.speech)
      this.speechPainter.draw(this.ctx, camera, sim, this.speech.getSnapshot());
  }
  get textureBytes(): number {
    let result = this.actorLayer.width * this.actorLayer.height * 4;
    for (const sprite of this.sprites.values()) result += spriteBytes(sprite);
    for (const sprite of this.floorTiles.values()) result += spriteBytes(sprite);
    for (const chunk of this.chunks.values()) result += spriteBytes(chunk.sprite);
    result += this.actorSprites.bytes;
    result += this.reactiveSprites.bytes;
    result += this.lia?.textureBytes ?? 0;
    return result;
  }
  destroy(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.ownActor = null;
    this.lia?.destroy();
    this.lia = null;
    for (const sprite of this.sprites.values()) freeSprite(sprite);
    for (const sprite of this.floorTiles.values()) freeSprite(sprite);
    for (const chunk of this.chunks.values()) freeSprite(chunk.sprite);
    this.sprites.clear();
    this.actorSprites.clear();
    this.reactiveSprites.clear();
    this.cosmetics.clear();
    this.floorTiles.clear();
    this.chunks.clear();
    this.floorEdges.clear();
    this.nameplates.clear();
    this.speechPainter.clear();
    this.privateProps.clear();
    this.signals.clear();
    this.acting = NEUTRAL_WORLD_ACTING;
    this.homeSignature = '';
    this.sorted = [];
    this.propIndex.clear();
    this.actorLayer.width = 0;
    this.actorLayer.height = 0;
    this.canvas.width = 1;
    this.canvas.height = 1;
  }
}
