import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { createSimulation } from '../simulation';
import { createCamera } from '../geometry';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
import { DEFAULT_AVATAR } from '../avatar-catalogue';
import { compilePoseSlots } from '../pose-slots';
import { projectPhotoScene } from '../photo-projection';
import { projectPhotoDecor } from '../photo-decor';

it('projects only own appearance, authored pose, companion and generic environment, with no private or peer fields', () => {
  const sim = createSimulation(WORLD);
  const marker = 'DO_NOT_EXPORT_PRIVATE_CONTEXT';
  sim.player.label = sim.player.publicId = marker;
  sim.player.appearance = { ...DEFAULT_AVATAR };
  sim.player.pose = compilePoseSlots(WORLD)[0];
  const input = {
    player: sim.player,
    bip: { ...sim.bip, label: marker },
    camera: createCamera({ width: 1280, height: 800 }, WORLD.spawn),
    time: 20,
    season: 'autumn' as const,
    atmosphere: { ...NEUTRAL_ATMOSPHERE, timezone: marker, time: 123456 },
    home: { palette: 'teal' as const },
    visitors: [{ alias: marker }],
    speech: marker,
    privateSignals: marker,
    game: { board: marker },
    notifications: marker,
    world: { props: [{ label: marker }] },
    decor: [
      {
        id: WORLD.props.find(prop => prop.kind === 'lamp')?.id ?? '',
        light: false,
        privateContent: marker,
      },
      { id: 'unknown-private-screen', screen: 3 as const, privateContent: marker },
    ],
  };
  const photo = projectPhotoScene(input);
  expect(JSON.stringify(photo)).not.toContain(marker);
  expect(photo.player.appearance).toEqual(DEFAULT_AVATAR);
  expect(photo.player.pose?.id).toBe(sim.player.pose.id);
  expect(photo.time).toBe(20);
  expect(photo.home?.palette).toBe('teal');
  expect(photo.decor).toHaveLength(1);
  expect(photo.decor[0].light).toBe(false);
  expect(Object.isFrozen(photo.player.position)).toBe(true);
  sim.player.position.x += 1;
  expect(photo.player.position.x).not.toBe(sim.player.position.x);
  expect(photo.atmosphere.time).toBeNull();
  expect(photo.atmosphere.timezone).toBeNull();
});

it('rejects non-finite geometry and captures no live simulation or face objects', () => {
  const sim = createSimulation(WORLD);
  const input = {
    player: sim.player,
    bip: sim.bip,
    camera: createCamera({ width: 320, height: 600 }, WORLD.spawn),
    time: 0,
    season: 'neutral' as const,
    atmosphere: NEUTRAL_ATMOSPHERE,
    home: null,
  };
  expect(() => projectPhotoScene({ ...input, time: NaN })).toThrow();
  expect(() =>
    projectPhotoScene({ ...input, camera: { ...input.camera, width: Infinity } })
  ).toThrow();
  const photo = projectPhotoScene(input);
  expect(Object.keys(photo.player)).not.toContain('path');
  expect(Object.keys(photo)).not.toContain('visitors');
  expect(sim.time).toBe(0);
  expect(sim.player.path).toEqual([]);
});
it('retains only finite authored screen variants and the latest local appearance, with no animation state', () => {
  const screen = WORLD.props.find(prop => prop.kind === 'display');
  if (!screen) throw new Error('Missing display');
  const result = projectPhotoDecor([
    { id: screen.id, screen: 0, machine: 0.4 },
    { id: screen.id, screen: 4 },
    { id: 'private', screen: 2 },
  ]);
  expect(result).toEqual([{ id: screen.id, screen: 4 }]);
  expect(Object.isFrozen(result[0])).toBe(true);
  expect(projectPhotoDecor()).toEqual([]);
  expect(projectPhotoDecor([{ id: screen.id }])).toEqual([]);
});
