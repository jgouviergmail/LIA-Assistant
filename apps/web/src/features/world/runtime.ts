import type { WorldSpeech } from './speech';
import { ScenePointer } from './scene-pointer';
import { SceneInteractions, type SceneHost } from './scene-interactions';
import { createCamera, project, zoomCamera } from './geometry';
import { createInput, type WorldInput } from './input';
import { nearbyWalkable } from './navigation';
import { FrameMeter, PaintCadence } from './performance';
import { WorldRenderer } from './renderer';
import {
  callBip,
  createSimulation,
  currentZone,
  directionFromScreen,
  stepSimulation,
  walkTo,
} from './simulation';
import type { Point, Quality, WorldDefinition, WorldSnapshot } from './types';
import type { WorldDriver } from './shared-simulation';
import type { HomeSkin } from './home-projection';
import type { Atmosphere } from './atmosphere';
import type { PrivateSignalPresentation } from './private-signal-projection';
import type { WorldActingSource } from './useWorldActingSource';
import { NEUTRAL_WORLD_ACTING, type WorldActingState } from './world-acting';
import { conversationFocusOffset } from './conversation-layout';
import type { Season } from './season';
import type { CosmeticActionId } from './cosmetic-interactions';
import { CosmeticController } from './cosmetic-controller';
import { EMOTE_SECONDS, type EmoteKind, type EmoteOutcome } from './emote-catalogue';
import type { PhotoScene } from './photo-projection';
export interface WorldRuntime {
  photoScene(): PhotoScene | null;
  /** A private local gesture, refused like the server would refuse a shared one. */
  emote(kind: EmoteKind): EmoteOutcome;
  setSeason(season: Season): void;
  input: WorldInput;
  interact(): void;
  zoom(factor: number): void;
  recenter(): void;
  explore(point: Point): void;
  callBip(): void;
  setReducedMotion(value: boolean): void;
  setQuality(quality: Quality): void;
  setPaused(paused: boolean): void;
  setHome(skin: HomeSkin | null): void;
  setAtmosphere(value: Atmosphere): void;
  setRouteVisible(value: boolean): void;
  setPrivateSignals(value: readonly PrivateSignalPresentation[]): void;
  setActingSource(source: WorldActingSource | undefined): void;
  setConversationOpen(open: boolean): void;
  snapshot(): WorldSnapshot;
  destroy(): void;
}
interface Options {
  onCosmeticCue?(action: CosmeticActionId, current: () => boolean, targetId: string): void;
  speech?: WorldSpeech;
  onInteract?(): void;
  scene?: SceneHost;
  driver?: WorldDriver;
  labels: { player: string; bip: string };
  reducedMotion: boolean;
  onSnapshot(value: WorldSnapshot): void;
  onFailure?(): void;
}
const STEP = 1 / 60;
type Cleanup = () => void;
function releaseResources(cleanups: Cleanup[]): unknown[] {
  const failures: unknown[] = [];
  for (const cleanup of cleanups.splice(0).reverse()) {
    try {
      cleanup();
    } catch (error) {
      failures.push(error);
    }
  }
  return failures;
}
export function createRuntime(
  canvas: HTMLCanvasElement,
  world: WorldDefinition,
  options: Options
): WorldRuntime {
  const cleanups: Cleanup[] = [];
  try {
    return mountRuntime(canvas, world, options, cleanups);
  } catch (error) {
    const failures = releaseResources(cleanups);
    if (failures.length)
      throw new AggregateError([error, ...failures], 'World initialization failed');
    throw error;
  }
}
function mountRuntime(
  canvas: HTMLCanvasElement,
  world: WorldDefinition,
  options: Options,
  cleanups: Cleanup[]
): WorldRuntime {
  const sim = createSimulation(world);
  const camera = createCamera({ width: 1, height: 1 }, world.spawn);
  const meter = new FrameMeter();
  const cadence = new PaintCadence();
  const renderer = new WorldRenderer(canvas, world, 'balanced', options.labels, options.speech);
  cleanups.push(() => renderer.destroy());
  const cosmetics = new CosmeticController(sim, {
    parent: options.scene,
    networked: !!options.driver,
    target: id => renderer.cosmeticTarget(id),
    activate: id => renderer.activateCosmetic(id, camera, sim),
    cancel: id => renderer.cancelCosmetic(id),
    cue: (action, current, targetId) => options.onCosmeticCue?.(action, current, targetId),
  });
  cleanups.push(() => cosmetics.cancel());
  const interactions = new SceneInteractions(sim, cosmetics);
  cleanups.push(() => interactions.cancel());
  const pointer = new ScenePointer(
    canvas,
    point => renderer.pick(point, sim),
    interactions,
    cosmetics
  );
  cleanups.push(() => pointer.clear());
  let quality: Quality = 'balanced',
    disposed = false,
    paused = false,
    frame = 0,
    last = 0,
    previousRender = 0,
    accumulator = 0,
    notified = 0;
  let walkAfterStand: { point: Point; running: boolean } | null = null;
  let actingSource: WorldActingSource | undefined;
  let conversationOpen = false;
  let actingState: WorldActingState = 'idle';
  let actingReadAt = -Infinity;
  let localEmoteSerial = 0;
  let localEmoteAfter = -Infinity;
  const stopMovement = () => {
    pointer.clear();
    cosmetics.cancel();
    walkAfterStand = null;
    interactions.cancel();
    sim.player.path = [];
    sim.player.running = false;
    input.clear();
  };
  function interact(): void {
    if (paused || disposed) return;
    input.clear();
    cosmetics.cancel();
    const target = interactions.nearest();
    if (target) interactions.choose(target);
    else options.onInteract?.();
  }
  function walkOnGround(point: Point, running: boolean): void {
    const goal = nearbyWalkable(sim.navigation, point);
    if (!goal) return;
    if (sim.player.pose) {
      if (interactions.choose({ kind: 'stand' })) walkAfterStand = { point: goal, running };
      return;
    }
    if (walkTo(sim, goal, running)) camera.following = true;
  }
  const input = createInput(canvas, camera, {
    interact,
    hover: point => pointer.move(point),
    walk: (point, running = false) => {
      if (paused) return;
      cosmetics.cancel();
      interactions.cancel();
      sim.player.running = false;
      const picked = renderer.pick(point, sim);
      const target = picked && picked !== 'self' ? interactions.resolve(picked) : picked;
      if (target === 'self') return;
      if (target && cosmetics.canOpen(target)) {
        if (interactions.choose(target)) camera.following = true;
        return;
      }
      walkOnGround(point, running);
    },
    changed: () => {
      limitCamera();
      // The canvas reads camera changes each frame; the HUD publishes at the bounded tick.
    },
  });
  cleanups.push(() => input.dispose());
  const resize = () => {
    const rect = canvas.getBoundingClientRect();
    camera.width = Math.max(1, rect.width);
    camera.height = Math.max(1, rect.height);
    renderer.resize(camera.width, camera.height);
    cadence.reset();
    limitCamera();
  };
  const observer = new ResizeObserver(resize);
  cleanups.push(() => observer.disconnect());
  observer.observe(canvas);
  function limitCamera(): void {
    const left = project({ x: 0, y: world.height }).x - 140,
      right = project({ x: world.width, y: 0 }).x + 140;
    camera.center.x = Math.max(left, Math.min(right, camera.center.x));
    camera.center.y = Math.max(
      -100,
      Math.min((world.width + world.height) * 16 + 100, camera.center.y)
    );
  }
  function snapshot(): WorldSnapshot {
    return {
      acting: actingState,
      player: { ...sim.player.position },
      bip: { ...sim.bip.position },
      zone: currentZone(sim),
      zoom: camera.zoom,
      following: camera.following,
      bipFollowing: sim.bipFollowing,
      hover: paused ? null : pointer.value,
      nearby: paused ? null : interactions.nearest(),
      metrics: {
        ...meter.read(renderer.drawCount, renderer.textureBytes),
        cosmeticEffects: renderer.activeCosmeticEffects,
      },
    };
  }
  function notify(): void {
    if (!disposed) options.onSnapshot(snapshot());
  }
  function advanceSimulation(): void {
    const direction = paused ? { x: 0, y: 0 } : directionFromScreen(input.direction());
    if (Math.hypot(direction.x, direction.y) > 0) {
      walkAfterStand = null;
      interactions.cancel();
      camera.following = true;
    }
    for (let count = 0; accumulator >= STEP && count < 6; count++) {
      if (options.driver) options.driver.step(sim, STEP, direction);
      else stepSimulation(sim, STEP, direction);
      accumulator -= STEP;
    }
  }
  function updateIntents(now: number): void {
    if (paused) return;
    if (walkAfterStand && !sim.player.pose) {
      walkTo(sim, walkAfterStand.point, walkAfterStand.running);
      walkAfterStand = null;
    }
    interactions.update();
    cosmetics.update();
    pointer.update(now, camera);
  }
  function tick(now: number): void {
    if (disposed || document.hidden) return;
    frame = requestAnimationFrame(tick);
    if (!last) {
      last = now;
      previousRender = now;
    }
    const elapsed = Math.min(0.1, (now - last) / 1000);
    last = now;
    accumulator = Math.min(0.1, accumulator + elapsed);
    advanceSimulation();
    updateIntents(now);
    options.speech?.advance(sim, now, paused);
    if (camera.following) {
      const target = project(sim.player.position);
      target.x += conversationFocusOffset(camera.width, camera.zoom, conversationOpen);
      target.y -= 28;
      const blend = options.reducedMotion ? 1 : Math.min(1, elapsed * 8);
      camera.center.x += (target.x - camera.center.x) * blend;
      camera.center.y += (target.y - camera.center.y) * blend;
    }
    limitCamera();
    // Private panels stop local input, but shared simulation still advances.
    // Painting behind the panel is bounded independently of that authority.
    if (!cadence.due(now, paused ? 30 : quality === 'low' ? 30 : 0)) return;
    const begin = performance.now();
    try {
      if (now - actingReadAt >= 100) {
        const acting = actingSource?.(Date.now()) ?? NEUTRAL_WORLD_ACTING;
        renderer.setActing(acting);
        actingState = acting.state;
        actingReadAt = now;
      }
      renderer.render(camera, sim, pointer.prop);
    } catch {
      fail();
      return;
    }
    meter.add(now - previousRender, performance.now() - begin);
    previousRender = now;
    if (now - notified > 200) {
      notified = now;
      notify();
    }
  }
  const visibility = () => {
    cancelAnimationFrame(frame);
    frame = 0;
    last = 0;
    previousRender = 0;
    accumulator = 0;
    meter.reset();
    cadence.reset();
    stopMovement();
    if (!document.hidden && !disposed) frame = requestAnimationFrame(tick);
  };
  document.addEventListener('visibilitychange', visibility);
  window.addEventListener('blur', stopMovement);
  canvas.addEventListener('blur', stopMovement);
  canvas.addEventListener('contextlost', fail);
  cleanups.push(() => document.removeEventListener('visibilitychange', visibility));
  cleanups.push(() => window.removeEventListener('blur', stopMovement));
  cleanups.push(() => canvas.removeEventListener('blur', stopMovement));
  cleanups.push(() => canvas.removeEventListener('contextlost', fail));
  cleanups.push(() => cancelAnimationFrame(frame));
  function destroy(): void {
    if (disposed) return;
    disposed = true;
    actingSource = undefined;
    if (releaseResources(cleanups).length) options.onFailure?.();
  }
  function fail(): void {
    destroy();
    options.onFailure?.();
  }
  resize();
  frame = requestAnimationFrame(tick);
  return {
    photoScene: () => (disposed ? null : renderer.photoScene(sim, camera)),
    emote: kind => {
      const now = performance.now() / 1000;
      if (disposed || paused || document.hidden || (options.driver && currentZone(sim) !== 'home'))
        return 'unavailable';
      if (now < localEmoteAfter) return 'rate_limited';
      localEmoteAfter = now + EMOTE_SECONDS;
      sim.player.emote = { kind, serial: ++localEmoteSerial, started: now, until: localEmoteAfter };
      notify();
      return 'accepted';
    },
    setSeason: value => {
      if (!disposed) renderer.setSeason(value);
    },
    input,
    setConversationOpen: value => {
      if (!disposed) conversationOpen = value;
    },
    setActingSource: value => {
      if (disposed) return;
      actingSource = value;
      actingReadAt = -Infinity;
    },
    setPrivateSignals: value => {
      if (!disposed) renderer.setPrivateSignals(value);
    },
    interact,
    snapshot,
    zoom: factor => {
      if (disposed || !Number.isFinite(factor) || factor <= 0) return;
      zoomCamera(camera, camera.zoom * factor, { x: camera.width / 2, y: camera.height / 2 });
      notify();
    },
    recenter: () => {
      if (disposed) return;
      camera.following = true;
      camera.center = project(sim.player.position);
      notify();
    },
    explore: point => {
      if (disposed || !Number.isFinite(point.x + point.y)) return;
      camera.following = false;
      camera.center = project(point);
      limitCamera();
      notify();
    },
    callBip: () => {
      if (disposed) return;
      if (sim.bipInteractionHeld) stopMovement();
      callBip(sim);
      notify();
    },
    setReducedMotion: value => {
      if (disposed) return;
      options.reducedMotion = value;
      renderer.reducedMotion = value;
    },
    setQuality: value => {
      if (disposed) return;
      quality = value;
      renderer.setQuality(value);
      resize();
      meter.reset();
    },
    setPaused: value => {
      if (disposed) return;
      paused = value;
      stopMovement();
    },
    setHome: skin => {
      if (!disposed) renderer.setHome(skin);
    },
    setAtmosphere: value => {
      if (!disposed) renderer.setAtmosphere(value);
    },
    setRouteVisible: value => {
      if (!disposed) renderer.showRoute = value;
    },
    destroy,
  };
}
