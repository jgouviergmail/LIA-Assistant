import { describe, expect, it } from 'vitest';
import { WORLD } from '../definition';
import {
  createCamera,
  panCamera,
  project,
  screenToWorld,
  worldToScreen,
  zoomCamera,
} from '../geometry';
import { compileNavigation, findRoute, isWalkable, moveActor } from '../navigation';
import {
  createSimulation,
  stepSimulation,
  walkTo,
  callBip,
  directionFromScreen,
} from '../simulation';

describe('world geometry and camera', () => {
  it('aligns an off-center actor inside its own cell before routing around a blocked corner', () => {
    const nav = { width: 4, height: 4, blocked: new Uint8Array(16) };
    nav.blocked[2 * nav.width + 2] = 1;
    const from = { x: 1.75, y: 1.95 };
    const route = findRoute(nav, from, { x: 2.5, y: 1.5 });
    expect(route[0]).toEqual({ x: 1.5, y: 1.5 });
  });
  it('round-trips world coordinates at several zooms and viewport sizes', () => {
    for (const size of [
      { width: 390, height: 700 },
      { width: 1440, height: 900 },
    ]) {
      const camera = createCamera(size, { x: 35, y: 27 });
      for (const zoom of [0.55, 1, 1.8]) {
        camera.zoom = zoom;
        for (const p of [
          { x: 0, y: 0 },
          { x: 71.4, y: 52.8 },
          { x: 27.25, y: 33.75 },
        ]) {
          const actual = screenToWorld(worldToScreen(p, camera), camera);
          expect(actual.x).toBeCloseTo(p.x, 8);
          expect(actual.y).toBeCloseTo(p.y, 8);
        }
      }
    }
  });

  it('anchors zoom to the pointer without moving the actor', () => {
    const camera = createCamera({ width: 800, height: 600 }, WORLD.spawn);
    const pointer = { x: 120, y: 430 };
    const before = screenToWorld(pointer, camera);
    zoomCamera(camera, 1.4, pointer);
    expect(screenToWorld(pointer, camera).x).toBeCloseTo(before.x);
    expect(screenToWorld(pointer, camera).y).toBeCloseTo(before.y);
    zoomCamera(camera, 100, pointer);
    expect(camera.zoom).toBe(1.8);
    zoomCamera(camera, -10, pointer);
    expect(camera.zoom).toBe(0.55);
  });

  it('pans in CSS pixels independently of device density and rejects invalid zoom', () => {
    const camera = createCamera({ width: 400, height: 600 }, WORLD.spawn);
    const center = { ...camera.center };
    panCamera(camera, { x: 90, y: -30 });
    expect(camera.center.x).toBeCloseTo(center.x - 90 / camera.zoom);
    expect(camera.center.y).toBeCloseTo(center.y + 30 / camera.zoom);
    const before = camera.zoom;
    zoomCamera(camera, Number.NaN, { x: 0, y: 0 });
    expect(camera.zoom).toBe(before);
    expect(project({ x: 1, y: 0 })).toEqual({ x: 32, y: 16 });
  });
});

describe('authored world and navigation', () => {
  const nav = compileNavigation(WORLD);
  it('keeps every authored place reachable from the spawn', () => {
    expect(new Set(WORLD.props.map(prop => prop.id)).size).toBe(WORLD.props.length);
    expect(isWalkable(nav, WORLD.spawn)).toBe(true);
    for (const zone of WORLD.zones) {
      expect(isWalkable(nav, zone.arrival), zone.id).toBe(true);
      expect(findRoute(nav, WORLD.spawn, zone.arrival).length, zone.id).toBeGreaterThan(0);
    }
  });

  it('does not route through furniture, water or diagonal corners', () => {
    const tiny = compileNavigation({
      ...WORLD,
      width: 5,
      height: 5,
      props: [
        {
          id: 'a',
          kind: 'planter',
          x: 1,
          y: 0,
          width: 1,
          depth: 1,
          height: 1,
          tone: 'sage',
          blocking: true,
        },
        {
          id: 'b',
          kind: 'planter',
          x: 0,
          y: 1,
          width: 1,
          depth: 1,
          height: 1,
          tone: 'sage',
          blocking: true,
        },
      ],
      grounds: [],
      zones: [],
    });
    expect(findRoute(tiny, { x: 0.5, y: 0.5 }, { x: 3.5, y: 3.5 })).toEqual([]);
    expect(isWalkable(tiny, { x: -0.1, y: 1 })).toBe(false);
    expect(isWalkable(tiny, { x: Number.NaN, y: 1 })).toBe(false);
    expect(findRoute(nav, WORLD.spawn, { x: Infinity, y: 2 })).toEqual([]);
  });

  it('bounds search work and returns no route for an unreachable destination', () => {
    expect(findRoute(nav, WORLD.spawn, WORLD.zones[1].arrival, 1)).toEqual([]);
    expect(findRoute(nav, WORLD.spawn, { x: -50, y: 0 })).toEqual([]);
  });

  it('slides along obstacles and never crosses map bounds on a stalled frame', () => {
    const start = { x: 0.5, y: 0.5 };
    const result = moveActor(nav, start, { x: -10, y: -10 });
    expect(isWalkable(nav, result)).toBe(true);
    expect(result.x).toBeGreaterThanOrEqual(0.22);
    expect(result.y).toBeGreaterThanOrEqual(0.22);
    expect(moveActor(nav, start, { x: Number.NaN, y: 1 })).toEqual(start);
  });
});

describe('local simulation', () => {
  it('normalizes screen-relative diagonal movement', () => {
    expect(Math.hypot(...Object.values(directionFromScreen({ x: 1, y: 1 })))).toBeCloseTo(1);
    expect(directionFromScreen({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
  });

  it('moves at the same speed at 30, 60 and 144 Hz', () => {
    const positions = [30, 60, 144].map(hz => {
      const sim = createSimulation(WORLD);
      for (let i = 0; i < hz; i++) stepSimulation(sim, 1 / hz, { x: 1, y: 0 });
      return sim.player.position;
    });
    expect(positions[0].x).toBeCloseTo(positions[1].x, 4);
    expect(positions[1].x).toBeCloseTo(positions[2].x, 4);
    expect(positions[0].y).toBeCloseTo(positions[2].y, 4);
  });

  it('bounds suspended time and invalid time, cancels a path on manual movement', () => {
    const sim = createSimulation(WORLD);
    const start = { ...sim.player.position };
    expect(walkTo(sim, WORLD.zones[1].arrival)).toBe(true);
    stepSimulation(sim, 100, { x: 1, y: 0 });
    expect(
      Math.hypot(sim.player.position.x - start.x, sim.player.position.y - start.y)
    ).toBeLessThan(0.4);
    expect(sim.player.path).toHaveLength(0);
    const current = { ...sim.player.position };
    stepSimulation(sim, Number.NaN, { x: 1, y: 0 });
    expect(sim.player.position).toEqual(current);
  });

  it('finishes a click path at the requested reachable destination', () => {
    const sim = createSimulation(WORLD);
    const goal = WORLD.zones[1].arrival;
    expect(walkTo(sim, goal)).toBe(true);
    for (let i = 0; i < 2400 && sim.player.path.length; i++)
      stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    expect(sim.player.path).toHaveLength(0);
    expect(sim.player.position.x).toBeCloseTo(goal.x, 1);
    expect(sim.player.position.y).toBeCloseTo(goal.y, 1);
  });

  it('keeps autonomous and called BIP on walkable ground', () => {
    const sim = createSimulation(WORLD);
    for (let i = 0; i < 1800; i++) {
      stepSimulation(sim, 1 / 30, { x: 0, y: 0 });
      expect(isWalkable(sim.navigation, sim.bip.position)).toBe(true);
    }
    callBip(sim);
    for (let i = 0; i < 900; i++) stepSimulation(sim, 1 / 60, { x: 0, y: 0 });
    expect(
      Math.hypot(
        sim.player.position.x - sim.bip.position.x,
        sim.player.position.y - sim.bip.position.y
      )
    ).toBeLessThan(2);
    expect(sim.bip.walking).toBe(false);
    expect(sim.bip.facing).toBe(1);
  });
});
