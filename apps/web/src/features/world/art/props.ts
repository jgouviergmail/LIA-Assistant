import type { AvatarAppearance } from '../avatar-catalogue';
import type { Season } from '../season';
import { NO_DECOR, type DecorPresentation, type PersonInteraction } from '../decor-presentation';
import { paintScreenContent } from './screen-content';
import { paintPond } from './pond';
import { paintSmartphone } from './smartphone';
import { paintRoomModel } from './room-models';
import { paintJoinedWall, paintParasol } from './joined-walls';
import {
  paintCounter,
  paintParcels,
  paintMailbox,
  paintTelephone,
  paintCalendar,
  paintClock,
  paintWritingDesk,
} from './activity-objects';
import { paintHerbarium, paintRadio } from './leisure';
import { Painter, type Sprite } from './painter';
import type { PropKind, Tone, WorldProp } from '../types';
import { actorBox, actorFace } from './actor-direction';
import { paintPerson } from './person';
import {
  paintGardenTree,
  paintGardenPlant,
  paintGardenPlanter,
  paintGardenFlowers,
} from './garden';
import { ACCENTS, WOOD, DARK } from './palette';
export { ACCENTS } from './palette';
import { paintWall, paintWallCorner } from './architecture';
import { paintTelescope } from './creative';
import { paintRug, paintDesk, paintBed, paintFountain, paintTable } from './interiors';
type Draw = (p: Painter, o: WorldProp) => void;
const DRAW: Record<PropKind, Draw> = {
  smartphone: paintSmartphone,
  pond: paintPond,
  sidetable: paintRoomModel,
  waterlily: paintRoomModel,
  sink: paintRoomModel,
  tablelamp: paintRoomModel,
  rock: paintRoomModel,
  reeds: paintRoomModel,
  cat: paintRoomModel,
  bench: paintRoomModel,
  display: paintRoomModel,
  billiards: paintRoomModel,
  arcade: paintRoomModel,
  poster: paintRoomModel,
  drawingtable: paintRoomModel,
  wallphone: paintRoomModel,
  callbook: paintRoomModel,
  archive: paintRoomModel,
  readingdesk: paintRoomModel,
  bar: paintRoomModel,
  bottles: paintRoomModel,
  jukebox: paintRoomModel,
  labtable: paintRoomModel,
  machine: paintRoomModel,
  weightbench: paintRoomModel,
  dumbbells: paintRoomModel,
  mirror: paintRoomModel,
  crystal: paintRoomModel,
  toilet: paintRoomModel,
  lounger: paintRoomModel,
  vegetable: paintRoomModel,
  nightstand: paintRoomModel,
  alarm: paintRoomModel,
  promiseboard: paintRoomModel,

  partition: paintJoinedWall,
  parasol: paintParasol,
  counter: paintCounter,
  parcels: paintParcels,
  mailbox: paintMailbox,
  telephone: paintTelephone,
  calendar: paintCalendar,
  clock: paintClock,
  writingdesk: paintWritingDesk,
  meetingtable: paintRoomModel,
  herbarium: paintHerbarium,
  radio: paintRadio,
  rug: paintRug,
  beam: (p, o) => {
    p.box(0, 0, 2.9, o.width, o.depth, 0.22, '#476b65');
    p.box(0, 0, 3.12, o.width, o.depth, 0.07, '#789389');
  },
  noticeboard: (p, o) => {
    p.box(0.1, 0.28, 0, 0.12, 0.18, 0.8, WOOD);
    p.box(o.width - 0.22, 0.28, 0, 0.12, 0.18, 0.8, WOOD);
    p.box(0, 0.15, 0.7, o.width, 0.24, 1.35, '#426d69');
    p.panel(0.12, 0.4, 0.84, o.width - 0.24, 1.05, '#bca77f');
    const paperWidth = Math.min(0.35, (o.width - 0.56) / 3),
      gap = (o.width - 0.44 - paperWidth * 3) / 2;
    for (let i = 0; i < 3; i++) {
      const x = 0.22 + i * (paperWidth + gap);
      p.panel(x, 0.42, 1.05 + (i % 2) * 0.16, paperWidth, 0.51, '#f2e8cf');
      p.panel(x + 0.04, 0.43, 1.38 + (i % 2) * 0.16, paperWidth - 0.08, 0.055, ACCENTS[o.tone]);
    }
  },
  mosaic: (p, o) => {
    p.box(0, 0, 0, o.width, o.depth, 0.025, '#6c9d95');
    p.box(0.14, 0.14, 0.025, o.width - 0.28, o.depth - 0.28, 0.025, '#d9dfc7');
    p.box(0.22, 0.22, 0.05, o.width - 0.44, o.depth - 0.44, 0.02, '#6c9d95');
    p.ctx.save();
    p.ctx.translate(0, 42);
    p.ctx.transform(1, 0.5, -1, 0.5, 0, 0);
    p.ctx.font = '700 24px system-ui, sans-serif';
    p.ctx.fillStyle = '#f4ecd6';
    p.ctx.textAlign = 'center';
    p.ctx.fillText('LIA', 0, 12);
    p.ctx.restore();
  },
  wallCorner: paintWallCorner,
  wall: (p, o) => paintWall(p, o, false, false),
  sideWall: (p, o) => paintWall(p, o, true, false),
  window: (p, o) => paintWall(p, o, false, true),
  sideWindow: (p, o) => paintWall(p, o, true, true),
  desk: paintDesk,
  chair: paintRoomModel,
  shelf: paintRoomModel,
  plant: paintGardenPlant,
  tree: paintGardenTree,
  sofa: paintRoomModel,
  table: paintTable,
  planter: paintGardenPlanter,
  lamp: p => {
    p.box(0.04, 0.04, 0, 0.35, 0.35, 0.09, DARK);
    p.box(0.18, 0.18, 0.09, 0.07, 0.07, 1.7, DARK);
    p.box(
      0.01,
      0.01,
      1.7,
      0.4,
      0.4,
      0.42,
      p.decor.light === false ? '#76857b' : p.decor.light ? '#ffe9a4' : '#e8d9a6'
    );
    for (const x of [0, 0.37]) for (const y of [0, 0.37]) p.box(x, y, 1.7, 0.04, 0.04, 0.42, DARK);
    p.box(-0.03, -0.03, 2.1, 0.48, 0.48, 0.07, DARK);
    p.box(0.05, 0.05, 2.17, 0.32, 0.32, 0.06, '#4c6265');
    p.box(0.15, 0.15, 2.23, 0.12, 0.12, 0.07, '#b69c62');
  },
  fountain: paintFountain,
  sign: (p, o) => {
    p.box(0.45, 0.35, 0, 0.12, 0.12, 0.65, DARK);
    p.box(0.05, 0.16, 0.55, 0.88, 0.2, 0.9, ACCENTS[o.tone]);
    p.panel(0.18, 0.37, 0.8, 0.62, 0.1, '#e9e6d6');
    p.panel(0.18, 0.37, 1.02, 0.4, 0.1, '#e9e6d6');
  },
  telescope: paintTelescope,
  easel: paintRoomModel,
  bed: paintBed,
  flowers: paintGardenFlowers,
};
export function paintProp(
  prop: WorldProp,
  ratio: number,
  shadow = true,
  season: Season = 'neutral',
  reaction = 0,
  decor: DecorPresentation = NO_DECOR
): Sprite {
  const painter = new Painter(
    prop.width,
    prop.depth,
    Math.max(prop.height, 2.5),
    ratio,
    season,
    reaction,
    decor
  );
  DRAW[prop.kind](painter, prop);
  paintScreenContent(painter, prop);
  if (
    shadow &&
    !prop.support &&
    prop.height > 0.1 &&
    prop.kind !== 'partition' &&
    prop.kind !== 'wallCorner' &&
    prop.kind !== 'wall' &&
    prop.kind !== 'sideWall' &&
    prop.kind !== 'window' &&
    prop.kind !== 'sideWindow'
  ) {
    // Composite behind the finished silhouette: stacked antialiasing must not
    // round to opaque pixels whose colour still depends on the shadow below.
    painter.ctx.save();
    painter.ctx.globalCompositeOperation = 'destination-over';
    painter.shadow(prop.width, prop.depth);
    painter.ctx.restore();
  }
  return painter.sprite();
}
type ActorBoxPainter = Painter['box'];
function robotDetails(p: Painter, box: ActorBoxPainter, facing: number): void {
  const face = actorFace(facing);
  if (face) {
    p.panel(face.x, face.y, 1.3, 0.63, 0.52, '#10263f', face.side);
    const eye = (offset: number) =>
      p.panel(
        face.side ? face.x + 0.01 : face.x + offset,
        face.side ? face.y + offset : face.y + 0.01,
        1.53,
        0.13,
        0.07,
        '#84dfe9',
        face.side
      );
    eye(0.09);
    eye(0.4);
    p.panel(
      face.side ? face.x : face.x + 0.23,
      face.side ? face.y + 0.23 : face.y,
      1.39,
      0.22,
      0.035,
      '#84dfe9',
      face.side
    );
  } else box(0.27, 0.13, 1.36, 0.46, 0.04, 0.13, '#285fae');
  p.box(0.26, 0.28, 1.95, 0.54, 0.5, 0.055, '#2863bc');
  box(0.04, 0.37, 1.4, 0.1, 0.3, 0.3, '#2863bc');
  box(0.93, 0.37, 1.4, 0.1, 0.3, 0.3, '#2863bc');
}
export function paintActor(
  bip: boolean,
  facing: number,
  phase: number,
  ratio: number,
  tone: Tone = 'violet',
  heading?: number,
  pose?: import('../pose-slots').PoseSlot | null,
  appearance?: AvatarAppearance,
  interaction?: PersonInteraction
): Sprite {
  if (!bip) return paintPerson(facing, phase, ratio, tone, heading, pose, appearance, interaction);
  const p = new Painter(1, 1, 2.6, ratio);
  const stride = Math.sin((phase * Math.PI) / 4) * 0.12;
  const cloth = '#e7e9df',
    dark = '#2863bc';
  const box = (x: number, y: number, z: number, w: number, d: number, h: number, color: string) => {
    const part = actorBox({ x, y, width: w, depth: d }, facing);
    p.box(part.x, part.y, z, part.width, part.depth, h, color);
  };
  box(0.26, 0.34 + stride, 0, 0.2, 0.32, 0.48, dark);
  box(0.58, 0.34 - stride, 0, 0.2, 0.32, 0.48, dark);
  box(0.21, 0.3 + stride, 0, 0.3, 0.44, 0.13, '#34434c');
  box(0.55, 0.3 - stride, 0, 0.3, 0.44, 0.13, '#34434c');
  box(0.16, 0.22, 0.48, 0.72, 0.56, 0.72, cloth);
  box(0.02, 0.25 - stride, 0.55, 0.18, 0.26, 0.56, '#4f95b7');
  box(0.9, 0.25 + stride, 0.55, 0.18, 0.26, 0.56, '#4f95b7');
  p.box(0.13, 0.16, 1.22, 0.8, 0.75, 0.72, '#e9ede5');
  robotDetails(p, box, facing);
  const result = p.sprite();
  return { ...result, anchorY: result.anchorY + 16 };
}
