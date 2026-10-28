/** A still has an explicit vocabulary; it never borrows live Canvas pixels or private DTOs. */
import { avatarAppearanceSchema } from './avatar-protocol';
import { DEFAULT_AVATAR, type AvatarAppearance } from './avatar-catalogue';
import { WORLD } from './definition';
import { compilePoseSlots, type PoseSlot } from './pose-slots';
import type { Actor, Camera, Point } from './types';
import type { HomeSkin } from './home-projection';
import type { Atmosphere } from './atmosphere';
import type { Season } from './season';
import { projectPhotoDecor, type PhotoDecor } from './photo-decor';

export interface PhotoActor {
  readonly position: Readonly<Point>;
  readonly facing: number;
  readonly walking: boolean;
  readonly phase: number;
  readonly appearance: AvatarAppearance;
  readonly pose: PoseSlot | null;
  readonly heading?: number;
}
export interface PhotoScene {
  readonly version: 1;
  readonly player: PhotoActor;
  readonly bip: PhotoActor;
  readonly camera: Readonly<Camera>;
  readonly time: number;
  readonly season: Season;
  readonly atmosphere: Readonly<Atmosphere>;
  readonly home: Readonly<HomeSkin> | null;
  readonly decor: readonly PhotoDecor[];
}
interface PhotoInput {
  player: Actor;
  bip: Actor;
  camera: Camera;
  time: number;
  season: Season;
  atmosphere: Atmosphere;
  home: HomeSkin | null;
  decor?: readonly PhotoDecor[];
}
const POSES = new Map(compilePoseSlots(WORLD).map(pose => [pose.id, pose]));
function finite(value: number, bound = 1e9): number {
  if (!Number.isFinite(value) || Math.abs(value) > bound) throw new Error('world_photo_geometry');
  return value;
}
function point(value: Point): Readonly<Point> {
  return Object.freeze({ x: finite(value.x), y: finite(value.y) });
}
function appearance(value: AvatarAppearance = DEFAULT_AVATAR): AvatarAppearance {
  return Object.freeze(
    avatarAppearanceSchema.parse({
      version: value.version,
      skin: value.skin,
      hair: value.hair,
      hair_color: value.hair_color,
      outfit: value.outfit,
      outfit_color: value.outfit_color,
      headwear: value.headwear,
      headwear_color: value.headwear_color,
      glasses: value.glasses,
    })
  );
}
function actor(value: Actor): PhotoActor {
  const authored = value.pose ? POSES.get(value.pose.id) : null;
  const pose = authored
    ? Object.freeze({
        ...authored,
        position: point(authored.position),
        approach: point(authored.approach),
      })
    : null;
  return Object.freeze({
    position: point(value.position),
    facing: Math.max(0, Math.min(3, Math.floor(finite(value.facing)))),
    walking: value.walking,
    phase: finite(value.phase) % 8,
    appearance: appearance(value.appearance),
    pose,
    heading: value.heading === undefined ? undefined : finite(value.heading),
  });
}
export function projectPhotoScene(input: PhotoInput): PhotoScene {
  const { camera, atmosphere } = input;
  if (camera.width <= 0 || camera.height <= 0 || camera.zoom <= 0)
    throw new Error('world_photo_geometry');
  return Object.freeze({
    version: 1,
    player: actor(input.player),
    bip: actor(input.bip),
    camera: Object.freeze({
      center: point(camera.center),
      width: finite(camera.width, 16384),
      height: finite(camera.height, 16384),
      zoom: finite(camera.zoom, 8),
      following: camera.following,
    }),
    time: Math.max(0, finite(input.time)),
    season: input.season,
    atmosphere: Object.freeze({
      phase: atmosphere.phase,
      weather: atmosphere.weather,
      sunny: atmosphere.sunny,
      time: null,
      timezone: null,
    }),
    home: input.home ? Object.freeze({ palette: input.home.palette }) : null,
    decor: projectPhotoDecor(input.decor),
  });
}
