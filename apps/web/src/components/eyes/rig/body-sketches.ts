/** Authored whole-character performances: phases unite body, limbs and facial intent. */
import type { BodyMotionSpace } from '../body-motion-geometry';
import { bodySceneTapes, type BodyScene, type ScenePose } from './body-scene';
import type { Tape } from './tape';
import type { RigCharacterId } from './acting-profile';

export const BODY_SKETCHES = [
  'body-hops',
  'body-doze',
  'body-sneeze',
  'body-balloon',
  'body-startle',
  'body-bow',
] as const;
export type BodySketchName = (typeof BODY_SKETCHES)[number];
const LOCAL: BodyMotionSpace = { minX: -0.45, maxX: 0.45, minY: -0.45, maxY: 0.12, roaming: false };
const HOME: ScenePose = {
  x: 0,
  y: 0,
  roll: 0,
  shape: [1, 1],
  support: 1,
  side: 0,
  arms: [0, 0],
  wrists: [0, 0],
  legs: [0, 0],
  feet: [0, 0],
  pitch: 0,
  face: [0, 0, 0, 0],
  blink: 0,
};

function hops(): BodyScene {
  return {
    duration: 3600,
    phases: [
      [90, { ...HOME, pitch: 0.07, face: [-0.04, 0, 0.12, 0] }],
      [
        230,
        {
          shape: [1.1, 0.9],
          arms: [-5, 4],
          wrists: [2, -2],
          pitch: 0.1,
          face: [-0.1, 0.02, 0.16, 0],
        },
      ],
      [
        340,
        {
          shape: [0.96, 1.07],
          arms: [11, -9],
          wrists: [-5, 4],
          legs: [-4, 3],
          feet: [5, -4],
          pitch: -0.16,
          flight: { height: 0.65, duration: 650 },
          face: [0.1, -0.09, 0.32, 0.1],
        },
      ],
      [
        650,
        {
          shape: [1, 1],
          arms: [7, -5],
          wrists: [4, -3],
          legs: [-2, 2],
          feet: [3, -3],
          pitch: -0.06,
        },
      ],
      [
        990,
        {
          shape: [1.15, 0.86],
          arms: [2, -2],
          wrists: [6, -5],
          legs: [0, 0],
          feet: [0, 0],
          pitch: 0.12,
          face: [-0.13, 0.03, 0.24, 0],
        },
      ],
      [1390, { ...HOME, wrists: [4, -1], pitch: 0.04, face: [-0.03, -0.04, 0.21, 0] }],
      [
        2240,
        {
          ...HOME,
          face: [-0.05, -0.02, 0.2, 0],
          character: { bip: { blinkR: 1, face: [-0.05, -0.02, 0.34, 0] } },
        },
      ],
      [2450, { character: { bip: { blinkR: 0, face: [-0.05, -0.02, 0.2, 0] } } }],
    ],
  };
}

function doze(): BodyScene {
  return {
    duration: 4800,
    spring: { frequency: 2.4, damping: 1 },
    phases: [
      [220, { ...HOME, side: 1 }],
      [
        580,
        {
          ...HOME,
          side: 1,
          roll: 4,
          arms: [-2, 1],
          wrists: [3, -2],
          pitch: 0.14,
          blink: 0.25,
          face: [-0.14, 0.03, -0.06, 0.03],
        },
      ],
      [
        1230,
        {
          support: 1,
          roll: 6,
          shape: [1.02, 0.98],
          arms: [-4, 2],
          wrists: [5, -4],
          legs: [0, 0],
          feet: [0, 0],
          pitch: 0.33,
          blink: 0.8,
          face: [-0.22, 0.05, -0.1, 0.04],
        },
      ],
      [
        1780,
        {
          roll: 7,
          shape: [1.03, 0.97],
          arms: [-4, 2],
          wrists: [5, -4],
          legs: [0, 0],
          feet: [0, 0],
          blink: 1,
        },
      ],
      [3250, { roll: 7, pitch: 0.33, blink: 1 }],
      [
        3500,
        {
          roll: 6,
          pitch: -0.15,
          blink: 0,
          arms: [9, -7],
          wrists: [-4, 3],
          face: [0.16, -0.12, -0.05, 0.18],
        },
      ],
      [
        3780,
        {
          roll: 0,
          shape: [1.02, 0.97],
          pitch: 0.08,
          arms: [3, -2],
          wrists: [3, -3],
          legs: [0, 0],
          feet: [0, 0],
        },
      ],
      [3980, { roll: 0, side: 1 }],
      [4100, { ...HOME, face: [-0.04, -0.02, 0.2, 0] }],
    ],
  };
}

function sneeze(): BodyScene {
  return {
    duration: 3400,
    phases: [
      [
        280,
        {
          ...HOME,
          shape: [0.99, 1.02],
          arms: [2, -1],
          wrists: [2, -1],
          pitch: -0.14,
          face: [0.04, -0.04, -0.04, 0.08],
        },
      ],
      [
        760,
        {
          roll: -3,
          shape: [0.95, 1.07],
          arms: [5, -3],
          wrists: [6, -3],
          pitch: -0.24,
          blink: 0.25,
          face: [-0.13, -0.1, -0.12, 0.2],
          character: { nimbo: { pitch: -0.33 } },
        },
      ],
      [
        1010,
        {
          roll: -3,
          shape: [0.95, 1.07],
          arms: [5, -3],
          wrists: [6, -3],
          pitch: -0.24,
          blink: 0.3,
          character: { nimbo: { pitch: -0.33 } },
        },
      ],
      [
        1170,
        {
          roll: 6,
          shape: [1.15, 0.86],
          arms: [-7, 4],
          wrists: [-4, 3],
          pitch: 0.35,
          blink: 1,
          face: [-0.3, 0.05, -0.1, 0.4],
          character: { nimbo: { pitch: 0.55 } },
        },
      ],
      [1280, { pitch: 0.35, character: { nimbo: { pitch: 0.55 } } }],
      [
        1390,
        {
          roll: -2,
          shape: [0.99, 1.03],
          arms: [4, -2],
          wrists: [5, -4],
          pitch: -0.1,
          blink: 0,
          face: [0.05, -0.04, 0.05, 0.05],
        },
      ],
      [
        1660,
        {
          roll: 1,
          shape: [1.02, 0.99],
          arms: [1, 0],
          wrists: [-1, 1],
          pitch: 0.05,
          face: [-0.03, 0, 0.12, 0],
        },
      ],
      [2080, { ...HOME, face: [-0.04, -0.02, 0.22, 0] }],
    ],
  };
}

function balloon(space: BodyMotionSpace, direction: number): BodyScene {
  const lift = Math.max(space.minY, space.roaming ? -0.85 : LOCAL.minY);
  const rises = lift < 0;
  const reach = space.roaming ? 0.75 : LOCAL.maxX;
  const x = rises ? Math.max(space.minX, Math.min(space.maxX, direction * reach)) : 0;
  const suspended: ScenePose = {
    x,
    y: lift,
    support: rises ? 0 : 1,
    shape: [0.94, 1.08],
    arms: [8, -3],
    wrists: [-4, 2],
    pitch: -0.12,
    gaze: direction * 0.34,
    face: [0.07, -0.04, 0.16, 0.02],
    character: { orbit: { gaze: direction * 0.54, pitch: -0.21 } },
  };
  return {
    duration: 4650,
    spring: { frequency: 3.1, damping: 1 },
    phases: [
      [
        310,
        {
          ...HOME,
          shape: [1.08, 0.94],
          pitch: 0.09,
          gaze: direction * 0.4,
          face: [0.03, -0.08, 0.05, 0.05],
        },
      ],
      [640, { support: rises ? 0 : 1, pitch: -0.19, arms: [6, -2], wrists: [1, -1] }],
      [1310, suspended],
      [2050, suspended],
      [
        2370,
        {
          gaze: 0,
          pitch: 0.14,
          face: [-0.03, -0.02, 0.25, 0],
          character: { orbit: { pitch: 0.22 } },
        },
      ],
      [
        3080,
        {
          x: 0,
          y: 0,
          support: rises ? 0 : 1,
          arms: [1, -2],
          wrists: [3, -1],
          shape: [1.08, 0.93],
        },
      ],
      [3220, { support: 1, pitch: 0.07, face: [-0.07, 0.01, 0.31, 0] }],
      [3670, { ...HOME, gaze: 0, face: [-0.02, -0.02, 0.2, 0] }],
    ],
  };
}

function startle(direction: number): BodyScene {
  return {
    duration: 3200,
    phases: [
      [70, { ...HOME, shape: [1.07, 0.94], pitch: 0.05, face: [-0.05, 0.01, -0.03, 0] }],
      [
        210,
        {
          roll: direction * 5,
          shape: [0.95, 1.09],
          arms: [13, -11],
          wrists: [-6, 5],
          legs: [-4, 4],
          feet: [5, -5],
          pitch: -0.17,
          flight: { height: 0.55, duration: 650 },
          face: [0.2, -0.14, -0.12, 0.35],
          character: {
            boulon: { gaze: direction * 0.45, pitch: -0.28, arms: [16, -5], wrists: [-3, 2] },
          },
        },
      ],
      [550, { shape: [1, 1], arms: [10, -8], wrists: [4, -3], legs: [-2, 2], feet: [3, -3] }],
      [
        860,
        {
          roll: -direction * 2,
          shape: [1.13, 0.88],
          arms: [2, -2],
          wrists: [6, -5],
          legs: [0, 0],
          feet: [0, 0],
          pitch: 0.13,
          face: [-0.14, 0.03, -0.02, 0.03],
        },
      ],
      [1210, { ...HOME, gaze: 0, face: [0.03, -0.05, 0.06, 0] }],
      [1760, { arms: [3, -2], wrists: [1, -1], face: [-0.05, -0.02, 0.22, 0] }],
      [2180, HOME],
    ],
  };
}

function bow(): BodyScene {
  const held: ScenePose = {
    y: 0,
    roll: 0,
    shape: [1.025, 0.975],
    support: 1,
    arms: [-5, -2],
    wrists: [4, -1],
    legs: [0, 0],
    feet: [0, 0],
    pitch: 0.46,
    character: {
      oscar: {
        pitch: 1.23,
        gaze: -0.14,
        arms: [-11, -2],
        wrists: [-8.5, -1],
        face: [-0.21, 0.01, 0.18, 0],
      },
    },
    face: [-0.13, -0.03, 0.24, 0],
  };
  return {
    duration: 3800,
    phases: [
      [170, { ...HOME, arms: [2, -1], pitch: -0.05, face: [0.02, -0.03, 0.1, 0] }],
      [
        430,
        { character: { oscar: { arms: [-9, -1], wrists: [-3, 0], pitch: 0.26, gaze: -0.08 } } },
      ],
      [700, held],
      [1410, held],
      [
        1950,
        {
          ...HOME,
          arms: [1, -1],
          wrists: [2, 0],
          pitch: 0.06,
          face: [-0.04, -0.03, 0.25, 0],
          character: { oscar: { gaze: 0, arms: [-2, -1], wrists: [-2, 0] } },
        },
      ],
      [
        2220,
        {
          ...HOME,
          wrists: [2, -1],
          pitch: 0,
          face: [-0.05, -0.02, 0.22, 0],
          character: { oscar: { wrists: [0, 0] } },
        },
      ],
      [2380, HOME],
    ],
  };
}

export function isBodySketchName(name: string): name is BodySketchName {
  return BODY_SKETCHES.some(candidate => candidate === name);
}

/** Entropy is consumed only when planning; body and limb timing have one phase authority. */
export function bodySketchTapes(
  name: BodySketchName,
  space: BodyMotionSpace = LOCAL,
  random: () => number = () => 0.5,
  identity?: RigCharacterId
): Tape[] {
  const direction = random() < 0.5 ? -1 : 1;
  const scenes: Record<BodySketchName, () => BodyScene> = {
    'body-hops': hops,
    'body-doze': doze,
    'body-sneeze': sneeze,
    'body-balloon': () => balloon(space, direction),
    'body-startle': () => startle(direction),
    'body-bow': bow,
  };
  return bodySceneTapes(scenes[name](), space, identity);
}
