/** Whole-character acting, played by the face's existing tape/spring clock. */
import type { BodyMotionSpace } from '@/components/eyes/body-motion-geometry';
import { absolute, bothSides, relative, type Keys } from '@/components/eyes/rig/choreo';
import type { SpringConfig } from '@/components/eyes/rig/spring';
import type { Tape } from '@/components/eyes/rig/tape';

export const BODY_SKETCHES = [
  'body-hops',
  'body-roll',
  'body-somersault',
  'body-doze',
  'body-sneeze',
  'body-balloon',
  'body-jig',
  'body-startle',
  'body-bow',
] as const;
export type BodySketchName = (typeof BODY_SKETCHES)[number];

const LOCAL: BodyMotionSpace = { minX: -0.45, maxX: 0.45, minY: -0.45, maxY: 0.12, roaming: false };
/** Critical damping keeps planned travel/scales within their geometric envelope. */
const BODY_SPRING: SpringConfig = { frequency: 4.6, damping: 1 };
const TURN_SPRING: SpringConfig = { frequency: 2.8, damping: 1 };
const DOZE_SPRING: SpringConfig = { frequency: 1.9, damping: 1 };
const FACE_SPRING: SpringConfig = { frequency: 3.8, damping: 0.9 };
type FacialBeat = readonly [time: number, eyes: number, brow: number, curve: number, open: number];
interface Scene {
  duration: number;
  x?: Keys;
  y?: Keys;
  roll?: Keys;
  sx?: Keys;
  sy?: Keys;
  face: readonly FacialBeat[];
  blink?: Keys;
  spring?: SpringConfig;
  /** Desired lift, used to find a lower temporary floor when no room remains above. */
  jumpHeight?: number;
  /** A complete unwrapped revolution, normalized only by the runtime on release. */
  terminalRoll?: number;
  pitch?: Keys;
}

function bound(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value)) + 0;
}
function bounded(keys: Keys, min: number, max: number): Keys {
  return keys.map(([time, value]) => [time, bound(value, min, max)] as const);
}
function timeline(keys: Keys = [], rest: number, duration: number, home = rest): Keys {
  return [[0, rest], ...keys, [duration - 650, home]];
}
function facialKeys(scene: Scene, column: 1 | 2 | 3 | 4): Keys {
  return timeline(
    scene.face.map(beat => [beat[0], beat[column]] as const),
    0,
    scene.duration
  );
}

function jumpKeys(scene: Scene, space: BodyMotionSpace): Keys | undefined {
  if (!scene.jumpHeight || !scene.y) return scene.y;
  const floor = bound(scene.jumpHeight + space.minY, 0, space.maxY);
  // The last authored beat returns to the real anchor, not the temporary floor.
  return scene.y.map(
    ([time, value], index, keys) =>
      [time, index === keys.length - 1 ? value : value + floor] as const
  );
}

function tapes(scene: Scene, space: BodyMotionSpace): Tape[] {
  const d = scene.duration;
  const body = (channel: Tape['channel'], keys: Keys) =>
    absolute(channel, keys, d, scene.spring ?? BODY_SPRING);
  return [
    body('bodyX', bounded(timeline(scene.x, 0, d), space.minX, space.maxX)),
    body('bodyY', bounded(timeline(jumpKeys(scene, space), 0, d), space.minY, space.maxY)),
    body('bodyRoll', timeline(scene.roll, 0, d, scene.terminalRoll ?? 0)),
    body('bodySx', timeline(scene.sx, 1, d)),
    body('bodySy', timeline(scene.sy, 1, d)),
    ...bothSides('sy', facialKeys(scene, 1), d - 40, FACE_SPRING),
    ...bothSides('browY', facialKeys(scene, 2), d - 40, FACE_SPRING),
    relative('mouthCurve', facialKeys(scene, 3), d, FACE_SPRING),
    relative('mouthOpen', facialKeys(scene, 4), d, FACE_SPRING),
    ...(scene.pitch ? [absolute('headPitch', timeline(scene.pitch, 0, d), d, FACE_SPRING)] : []),
    ...(scene.blink
      ? [
          absolute('blinkL', timeline(scene.blink, 0, d), d, BODY_SPRING),
          absolute('blinkR', timeline(scene.blink, 0, d), d, BODY_SPRING),
        ]
      : []),
  ];
}

function hops(): Scene {
  return {
    duration: 3600,
    pitch: [
      [150, 0.08],
      [420, -0.16],
      [920, 0.1],
      [1240, 0],
      [1740, -0.12],
      [2440, 0],
    ],
    jumpHeight: 0.65,
    y: [
      [150, 0.1],
      [420, -0.65],
      [920, 0.07],
      [1240, 0],
      [1500, 0.08],
      [1740, -0.42],
      [2140, 0.06],
      [2440, 0],
    ],
    sx: [
      [150, 1.15],
      [420, 0.89],
      [920, 1.24],
      [1240, 1],
      [1500, 1.1],
      [1740, 0.92],
      [2140, 1.17],
      [2440, 1],
    ],
    sy: [
      [150, 0.84],
      [420, 1.19],
      [920, 0.78],
      [1240, 1],
      [1500, 0.9],
      [1740, 1.12],
      [2140, 0.85],
      [2440, 1],
    ],
    face: [
      [150, -0.15, 0.03, 0.12, 0],
      [420, 0.1, -0.1, 0.38, 0.14],
      [920, -0.2, 0.05, 0.32, 0.05],
      [1740, 0.08, -0.08, 0.4, 0.12],
      [2440, -0.08, -0.03, 0.2, 0],
    ],
  };
}

function roll(direction: number): Scene {
  return {
    duration: 3800,
    pitch: [
      [180, 0.08],
      [600, -0.12],
      [1550, 0.1],
      [2200, -0.08],
      [2550, 0],
    ],
    spring: TURN_SPRING,
    terminalRoll: direction * 360,
    x: [
      [180, -direction * 0.1],
      [600, direction * 0.2],
      [1050, direction * 0.55],
      [1600, direction * 0.3],
      [2200, 0],
    ],
    roll: [
      [180, -direction * 12],
      [600, direction * 80],
      [1050, direction * 190],
      [1550, direction * 290],
      [2050, direction * 360],
    ],
    sx: [
      [180, 1.12],
      [600, 0.94],
      [1550, 1.08],
      [2200, 1.19],
      [2550, 1],
    ],
    sy: [
      [180, 0.88],
      [600, 1.06],
      [1550, 0.94],
      [2200, 0.83],
      [2550, 1],
    ],
    face: [
      [180, -0.1, 0.03, 0.06, 0],
      [600, 0.12, -0.13, 0.22, 0.18],
      [1550, -0.18, -0.08, 0.35, 0.1],
      [2550, -0.08, -0.03, 0.23, 0],
    ],
  };
}

function somersault(direction: number): Scene {
  return {
    duration: 4000,
    pitch: [
      [180, 0.12],
      [520, -0.2],
      [1380, 0.2],
      [1960, 0.15],
      [2380, 0],
    ],
    jumpHeight: 0.9,
    spring: TURN_SPRING,
    terminalRoll: direction * 360,
    x: [
      [520, direction * 0.2],
      [1320, direction * 0.35],
      [2150, 0],
    ],
    y: [
      [180, 0.12],
      [520, -0.9],
      [1320, -0.7],
      [1960, 0.1],
      [2380, 0],
    ],
    roll: [
      [180, -direction * 14],
      [520, direction * 70],
      [960, direction * 180],
      [1380, direction * 270],
      [1900, direction * 360],
    ],
    sx: [
      [180, 1.22],
      [520, 0.88],
      [1380, 0.95],
      [1960, 1.26],
      [2380, 1],
    ],
    sy: [
      [180, 0.8],
      [520, 1.24],
      [1380, 1.07],
      [1960, 0.76],
      [2380, 1],
    ],
    face: [
      [180, -0.2, 0.04, 0.1, 0],
      [520, 0.12, -0.13, 0.4, 0.2],
      [1380, -0.12, -0.06, 0.3, 0.14],
      [1960, -0.25, 0.04, 0.25, 0],
      [2380, -0.08, -0.04, 0.32, 0],
    ],
  };
}

function doze(): Scene {
  return {
    duration: 4800,
    pitch: [
      [600, 0.14],
      [1450, 0.32],
      [3300, 0.32],
      [3650, -0.2],
      [3980, 0],
    ],
    spring: DOZE_SPRING,
    y: [
      [600, 0.05],
      [1450, 0.12],
      [3340, 0.07],
      [3650, -0.18],
      [3980, 0],
    ],
    roll: [
      [600, 16],
      [1450, 75],
      [1850, 90],
      [3300, 90],
      [3650, -8],
      [3980, 0],
    ],
    sx: [
      [1450, 1.08],
      [3650, 0.94],
      [3980, 1],
    ],
    sy: [
      [1450, 0.92],
      [3650, 1.12],
      [3980, 1],
    ],
    blink: [
      [600, 0.35],
      [1450, 1],
      [3300, 1],
      [3550, 0],
    ],
    face: [
      [600, -0.18, 0.04, -0.08, 0.04],
      [1450, -0.28, 0.07, -0.12, 0.06],
      [3300, -0.28, 0.07, -0.12, 0.06],
      [3550, 0.2, -0.17, -0.08, 0.24],
      [3980, 0, -0.04, 0.18, 0],
    ],
  };
}

function sneeze(): Scene {
  return {
    duration: 3400,
    pitch: [
      [350, -0.22],
      [850, 0.25],
      [1200, -0.32],
      [1510, 0.1],
      [1940, 0],
    ],
    y: [
      [350, -0.05],
      [850, -0.12],
      [1200, 0.12],
      [1510, -0.09],
      [1940, 0],
    ],
    roll: [
      [350, -3],
      [850, -8],
      [1200, 12],
      [1510, -4],
      [1940, 0],
    ],
    sx: [
      [350, 0.98],
      [850, 0.93],
      [1200, 1.26],
      [1510, 0.94],
      [1940, 1],
    ],
    sy: [
      [350, 1.04],
      [850, 1.12],
      [1200, 0.76],
      [1510, 1.08],
      [1940, 1],
    ],
    blink: [
      [850, 0.35],
      [1200, 1],
      [1430, 0],
    ],
    face: [
      [350, 0.04, -0.08, -0.08, 0.12],
      [850, -0.22, -0.12, -0.16, 0.24],
      [1200, -0.35, 0.06, -0.18, 0.52],
      [1510, 0.1, -0.1, 0.08, 0.12],
      [1940, -0.06, -0.03, 0.22, 0],
    ],
  };
}

function flightAxis(min: number, max: number, random: () => number): number {
  const side = random() < 0.5 ? min : max;
  const available = side === 0 ? min + max : side;
  return available * (0.3 + 0.55 * bound(random(), 0, 1));
}

function balloon(space: BodyMotionSpace, direction: number, random: () => number): Scene {
  // Flight uses measured room only in the widget; cards perform the same joke locally.
  const limits = space.roaming
    ? space
    : {
        minX: Math.max(space.minX, LOCAL.minX),
        maxX: Math.min(space.maxX, LOCAL.maxX),
        minY: Math.max(space.minY, LOCAL.minY),
        maxY: Math.min(space.maxY, LOCAL.maxY),
      };
  const points = [900, 1550, 2250, 2870].map(time => ({
    time,
    x: flightAxis(limits.minX, limits.maxX, random),
    y: flightAxis(limits.minY, limits.maxY, random),
  }));
  const drift = limits.minY < 0 ? Math.max(limits.minY, -0.08) : Math.min(limits.maxY * 0.12, 0.2);
  return {
    duration: 4900,
    pitch: [
      [350, 0.18],
      [650, -0.18],
      [900, 0.25],
      [2870, -0.15],
      [3480, 0.18],
      [4250, 0],
    ],
    spring: TURN_SPRING,
    terminalRoll: direction * 720,
    x: [...points.map(point => [point.time, point.x] as const), [3480, 0]],
    y: [[350, drift], ...points.map(point => [point.time, point.y] as const), [3480, 0]],
    roll: [
      [350, -direction * 8],
      [900, direction * 100],
      [1550, direction * 260],
      [2250, direction * 430],
      [2870, direction * 600],
      [3480, direction * 720],
    ],
    sx: [
      [350, 1.12],
      [650, 0.48],
      [900, 0.55],
      [1550, 0.42],
      [2250, 0.54],
      [2870, 0.45],
      [3480, 0.6],
      [3800, 1.16],
    ],
    sy: [
      [350, 1.1],
      [650, 0.42],
      [900, 0.4],
      [1550, 0.53],
      [2250, 0.38],
      [2870, 0.52],
      [3480, 0.6],
      [3800, 1.12],
    ],
    face: [
      [350, 0.1, -0.08, 0.06, 0.18],
      [650, -0.18, -0.15, -0.2, 0.08],
      [900, 0.18, -0.16, -0.12, 0.24],
      [2250, -0.12, -0.09, 0.16, 0.15],
      [3480, -0.2, 0.05, 0.08, 0],
      [3800, -0.06, -0.06, 0.35, 0.08],
    ],
  };
}

function jig(direction: number): Scene {
  return {
    duration: 3900,
    pitch: [
      [350, -0.12],
      [650, 0.08],
      [850, -0.14],
      [1150, 0.08],
      [1850, -0.12],
      [2350, 0],
    ],
    x: [
      [350, -direction * 0.18],
      [850, direction * 0.2],
      [1350, -direction * 0.2],
      [1850, direction * 0.18],
      [2350, 0],
    ],
    y: [
      [350, -0.16],
      [650, 0.05],
      [850, -0.2],
      [1150, 0.05],
      [1350, -0.18],
      [1650, 0.05],
      [1850, -0.16],
      [2200, 0],
    ],
    roll: [
      [350, -direction * 12],
      [850, direction * 12],
      [1350, -direction * 10],
      [1850, direction * 10],
      [2350, 0],
    ],
    sx: [
      [350, 0.95],
      [650, 1.12],
      [850, 0.93],
      [1150, 1.13],
      [1350, 0.94],
      [1650, 1.12],
      [2200, 1],
    ],
    sy: [
      [350, 1.09],
      [650, 0.91],
      [850, 1.1],
      [1150, 0.9],
      [1350, 1.1],
      [1650, 0.92],
      [2200, 1],
    ],
    face: [
      [350, -0.13, -0.08, 0.35, 0.1],
      [850, -0.18, 0.02, 0.4, 0.12],
      [1350, -0.12, -0.1, 0.35, 0.1],
      [1850, -0.18, 0.02, 0.4, 0.12],
      [2350, -0.05, -0.04, 0.2, 0],
    ],
  };
}

function startle(direction: number): Scene {
  return {
    duration: 3200,
    pitch: [
      [100, 0.07],
      [330, -0.2],
      [920, 0.16],
      [1350, 0],
    ],
    jumpHeight: 0.55,
    y: [
      [100, 0.08],
      [330, -0.55],
      [920, 0.1],
      [1350, 0],
    ],
    roll: [
      [100, -direction * 3],
      [330, direction * 10],
      [920, -direction * 4],
      [1350, 0],
    ],
    sx: [
      [100, 1.14],
      [330, 0.86],
      [920, 1.24],
      [1350, 1],
    ],
    sy: [
      [100, 0.86],
      [330, 1.26],
      [920, 0.78],
      [1350, 1],
    ],
    face: [
      [100, -0.12, 0.04, -0.04, 0],
      [330, 0.23, -0.18, -0.16, 0.48],
      [920, -0.25, 0.04, -0.06, 0.08],
      [1350, 0.05, -0.07, 0.12, 0],
      [2100, -0.08, -0.03, 0.26, 0],
    ],
  };
}

function bow(): Scene {
  return {
    duration: 3800,
    y: [
      [180, -0.025],
      [650, 0.12],
      [1100, 0.12],
      [1400, -0.08],
      [1750, 0.04],
      [2100, 0],
    ],
    roll: [
      [180, -3],
      [650, 3],
      [1100, 3],
      [1400, -5],
      [1750, 2],
      [2100, 0],
    ],
    sx: [
      [180, 0.98],
      [650, 1.08],
      [1100, 1.08],
      [1400, 0.96],
      [2100, 1],
    ],
    sy: [
      [180, 1.03],
      [650, 0.89],
      [1100, 0.89],
      [1400, 1.1],
      [2100, 1],
    ],
    pitch: [
      [180, -0.08],
      [650, 0.7],
      [1100, 0.7],
      [1400, -0.26],
      [1750, 0.12],
      [2100, 0],
    ],
    face: [
      [180, 0.04, -0.03, 0.08, 0],
      [650, -0.16, -0.05, 0.24, 0.02],
      [1100, -0.16, -0.05, 0.24, 0.02],
      [1400, 0.12, -0.12, 0.06, 0.14],
      [1750, -0.06, -0.03, 0.2, 0],
      [2100, 0, 0, 0, 0],
    ],
  };
}

export function isBodySketchName(name: string): name is BodySketchName {
  return BODY_SKETCHES.some(candidate => candidate === name);
}

/** Pure planning: entropy and the safe travel envelope are supplied by the existing owner. */
export function bodySketchTapes(
  name: BodySketchName,
  space: BodyMotionSpace = LOCAL,
  random: () => number = () => 0.5
): Tape[] {
  const direction = random() < 0.5 ? -1 : 1;
  const scenes: Record<BodySketchName, () => Scene> = {
    'body-hops': hops,
    'body-roll': () => roll(direction),
    'body-somersault': () => somersault(direction),
    'body-doze': doze,
    'body-sneeze': sneeze,
    'body-balloon': () => balloon(space, direction, random),
    'body-jig': () => jig(direction),
    'body-startle': () => startle(direction),
    'body-bow': bow,
  };
  return tapes(scenes[name](), space);
}
