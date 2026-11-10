/** Behavioral contracts for anatomy-aware motion on the existing rig clock. */
import { describe, expect, it } from 'vitest';
import { RIG_EYE_STYLE_IDS } from '../../eye-styles';
import type { EyeExpression } from '../../expression-engine';
import type { RigCharacterId } from '../acting-profile';
import { BODY_SKETCHES } from '../body-sketches';
import { LIMB_CHANNELS, type ChannelValues } from '../channels';
import { actingSketchTapes } from '../acting-scenes';
import { resolveActingProfile } from '../acting-profile';
import { warpTapes } from '../choreo';
import { NEUTRAL_CONTEXT } from '../direction';
import { createLifeRandom } from '../life';
import { createEyeRig, type EyeRig } from '../runtime';
import { createSketchClock } from '../sketches';

const JOINTS = ['armL', 'armR', 'wristL', 'wristR', 'legL', 'legR', 'footL', 'footR'] as const;
const ARMS = ['armL', 'armR', 'wristL', 'wristR'] as const;
const LEGS = ['legL', 'legR', 'footL', 'footR'] as const;

function actor(characterId: RigCharacterId = 'bip', expression: EyeExpression = 'neutral') {
  return createEyeRig({
    characterId,
    initial: { expression, styleId: 'cozmo', family: 'calm' },
  });
}

function run(rig: EyeRig, duration: number, observe?: (values: Readonly<ChannelValues>) => void) {
  for (let time = 0; time < duration; time += 16) {
    rig.step(Math.min(16, duration - time));
    observe?.(rig.values());
  }
}

describe('native limbs', () => {
  it('moves every visible joint independently through an authored hop', () => {
    const rig = actor();
    rig.setBodySpace({ minX: -1, maxX: 1, minY: -1, maxY: 1, roaming: false });
    rig.playScene('body-hops');
    const traces = JOINTS.map(() => [] as number[]);
    run(rig, 20_000, values => {
      JOINTS.forEach((key, index) => traces[index].push(values[key]));
    });
    for (const values of traces) {
      expect(Math.max(...values) - Math.min(...values)).toBeGreaterThan(1.5);
      expect(values.every(Number.isFinite)).toBe(true);
    }
    expect(traces[0]).not.toEqual(traces[1]);
    expect(traces[2]).not.toEqual(traces[0]);
    expect(traces[4]).not.toEqual(traces[6]);
    expect(rig.isSettling()).toBe(false);
  });

  it.each([...RIG_EYE_STYLE_IDS, 'orbit'] satisfies RigCharacterId[])(
    'does not invent limbs on %s in any contextual or scene motion',
    characterId => {
      const rig = actor(characterId, 'speaking');
      run(rig, 1_200, values => JOINTS.forEach(key => expect(values[key]).toBe(0)));
      rig.setPose({ expression: 'neutral', styleId: 'cozmo', family: 'calm' });
      rig.playScene('body-startle');
      run(rig, 4_000, values => JOINTS.forEach(key => expect(values[key]).toBe(0)));
    }
  );

  it.each(['spirit', 'nimbo'] satisfies RigCharacterId[])('never invents legs on %s', id => {
    const rig = actor(id, 'speaking');
    let armTravel = 0;
    run(rig, 6_000, values => {
      LEGS.forEach(key => expect(values[key]).toBe(0));
      armTravel = Math.max(armTravel, Math.abs(values.armL), Math.abs(values.armR));
    });
    expect(armTravel).toBeGreaterThan(3);
  });

  it('distinguishes attentive opening from a one-sided thought and keeps the feet quiet', () => {
    const listen = actor('bip', 'attentive');
    const think = actor('bip', 'thinking');
    run(listen, 3_000);
    run(think, 3_000);
    expect(listen.values().armL).toBeGreaterThan(3);
    expect(listen.values().armR).toBeLessThan(-3);
    expect(think.values().wristL - listen.values().wristL).toBeGreaterThan(3);
    expect(Math.abs(think.values().armR)).toBeLessThan(4);
    LEGS.forEach(key => expect(Math.abs(think.values()[key])).toBeLessThan(3));
  });

  it('carries expression intensity into the gesture while preserving its bounded anatomy', () => {
    const mild = createEyeRig({
      characterId: 'bip',
      initial: { expression: 'joy', styleId: 'cozmo', family: 'calm', emphasis: 0.5 },
      idleScale: 0,
    });
    const strong = createEyeRig({
      characterId: 'bip',
      initial: { expression: 'joy', styleId: 'cozmo', family: 'calm', emphasis: 1.4 },
      idleScale: 0,
    });
    expect(strong.values().armL - mild.values().armL).toBeGreaterThan(4);
  });

  it('starts an initially static attentive portrait from the original pose when resumed', () => {
    const rig = createEyeRig({
      characterId: 'bip',
      initial: { expression: 'attentive', styleId: 'cozmo', family: 'calm' },
      reducedMotion: true,
      idleScale: 0,
    });
    expect(rig.values().armL).toBe(0);
    rig.setReducedMotion(false);
    rig.step(1);
    expect(Math.abs(rig.values().armL)).toBeLessThan(0.1);
    run(rig, 2_000);
    expect(rig.values().armL).toBeGreaterThan(3);
  });

  it('resumes an attentive pose after reduced motion interrupted an already-settled rig', () => {
    const rig = actor('bip', 'attentive');
    rig.setIdleScale(0);
    run(rig, 3_000);
    expect(rig.isSettling()).toBe(false);
    rig.setReducedMotion(true);
    expect(rig.values().armL).toBe(0);
    rig.setReducedMotion(false);
    run(rig, 2_000);
    expect(rig.values().armL).toBeGreaterThan(3);
  });

  it('releases speech gestures during long phrase pauses without following every syllable', () => {
    const rig = actor('bip', 'speaking');
    rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'calculating' });
    rig.setIdleScale(0);
    let quietMs = 0;
    let releaseCount = 0;
    let peaks = 0;
    let previous = 0;
    run(rig, 25_000, values => {
      const energy = Math.max(...ARMS.map(key => Math.abs(values[key])));
      if (energy > 4 && previous <= 4) peaks += 1;
      previous = energy;
      quietMs = values.mouthOpen < 0.015 ? quietMs + 16 : 0;
      if (quietMs >= 450) {
        expect(energy).toBeLessThan(1.5);
        releaseCount += 1;
      }
    });
    expect(peaks).toBeGreaterThan(2);
    expect(peaks).toBeLessThan(24);
    expect(releaseCount).toBeGreaterThan(4);
  });

  it('gives resting limbs a readable occasional beat on the existing facial-life cue', () => {
    const clock = createSketchClock();
    clock.dueMs = 600_000;
    const rig = createEyeRig({
      characterId: 'bip',
      lifeRandom: createLifeRandom(29),
      sketchClock: clock,
      idleScale: 0,
    });
    let arm = 0;
    let foot = 0;
    for (let cue = 0; cue < 8; cue++) {
      rig.answerIn(0);
      run(rig, 3500, values => {
        arm = Math.max(arm, Math.abs(values.armL), Math.abs(values.armR));
        foot = Math.max(foot, Math.abs(values.footL), Math.abs(values.footR));
        expect(values.headYaw).toBe(0);
        expect(values.headPitch).toBe(0);
        expect(rig.isPerforming()).toBe(false);
      });
    }
    expect(arm).toBeGreaterThan(7);
    expect(foot).toBeGreaterThan(4);
    rig.setLifePaused(true);
    run(rig, 3_000);
    JOINTS.forEach(key => expect(rig.values()[key]).toBeCloseTo(0, 3));
  });

  it.each(['moss', 'lumen'] satisfies RigCharacterId[])(
    'moves the drawn arms and feet without inventing wrists or separate legs on %s',
    id => {
      const rig = actor(id);
      rig.playScene('body-hops');
      let footTravel = 0;
      run(rig, 12_000, values => {
        for (const key of ['wristL', 'wristR', 'legL', 'legR'] as const)
          expect(values[key]).toBe(0);
        footTravel = Math.max(footTravel, Math.abs(values.footL));
      });
      expect(footTravel).toBeGreaterThan(1);
    }
  );

  it('warps one authored timeline while retaining intentional wrist overlap', () => {
    const tapes = actingSketchTapes(
      'body-hops',
      resolveActingProfile('bip', 'cozmo'),
      { minX: -1, maxX: 1, minY: -1, maxY: 1, roaming: false },
      createLifeRandom(25)
    );
    const warped = warpTapes(tapes, createLifeRandom(31));
    const body = warped.find(tape => tape.channel === 'bodySy');
    expect(body).toBeDefined();
    for (const channel of LIMB_CHANNELS) {
      const limb = warped.find(tape => tape.channel === channel);
      const original = tapes.find(tape => tape.channel === channel)!;
      const pace = body!.durationMs! / tapes.find(tape => tape.channel === 'bodySy')!.durationMs!;
      expect(limb).toBeDefined();
      limb!.keys.forEach((key, index) =>
        expect(Math.abs(key.atMs - original.keys[index].atMs * pace)).toBeLessThan(1.1)
      );
    }
    expect(warped.find(tape => tape.channel === 'wristL')!.keys[1].atMs).toBeGreaterThan(
      warped.find(tape => tape.channel === 'armL')!.keys[1].atMs
    );
  });

  it('bounds long mixed performances and releases all old joints when identity changes', () => {
    const rig = createEyeRig({ characterId: 'bip', lifeRandom: createLifeRandom(17) });
    const feelings: EyeExpression[] = ['joy', 'surprise', 'thinking', 'attentive', 'speaking'];
    for (const expression of feelings) {
      rig.setPose({ expression, styleId: 'cozmo', family: 'lively', emphasis: 2 });
      run(rig, 20_000, values => {
        ARMS.forEach(key => expect(Math.abs(values[key])).toBeLessThanOrEqual(18));
        LEGS.forEach(key => expect(Math.abs(values[key])).toBeLessThanOrEqual(10));
      });
    }
    rig.setCharacterId('orbit');
    run(rig, 3_000, values => JOINTS.forEach(key => expect(values[key]).toBe(0)));
  });

  it.each(BODY_SKETCHES)('lets the limbs participate in %s then releases its pose', scene => {
    const rig = actor();
    const rest = actor();
    rig.setIdleScale(0);
    rest.setIdleScale(0);
    rig.playScene(scene);
    let travel = 0;
    run(rig, 8_000, values => {
      travel = Math.max(travel, ...JOINTS.map(key => Math.abs(values[key])));
    });
    expect(travel).toBeGreaterThan(3);
    JOINTS.forEach(key => expect(rig.values()[key]).toBeCloseTo(rest.values()[key], 2));
  });

  it('interrupts a scene continuously and cannot resume the abandoned limb gesture', () => {
    const rig = actor();
    rig.setIdleScale(0);
    rig.playScene('body-hops');
    run(rig, 600);
    const before = { ...rig.values() };
    expect(Math.abs(before.armL)).toBeGreaterThan(3);
    rig.setContext({ ...NEUTRAL_CONTEXT, activity: 'calculating' });
    JOINTS.forEach(key => expect(rig.values()[key]).toBe(before[key]));
    rig.step(1);
    JOINTS.forEach(key => expect(Math.abs(rig.values()[key] - before[key])).toBeLessThan(0.5));
    run(rig, 5_000);
    const after = { ...rig.values() };
    run(rig, 5_000);
    JOINTS.forEach(key => expect(rig.values()[key]).toBeCloseTo(after[key], 3));
    expect(rig.isPerforming()).toBe(false);
  });

  it('uses the existing speech entropy without changing the facial performance', () => {
    const supported = createEyeRig({ characterId: 'bip', lifeRandom: createLifeRandom(98) });
    const unsupported = createEyeRig({ characterId: 'cozmo', lifeRandom: createLifeRandom(98) });
    for (const rig of [supported, unsupported])
      rig.setPose({ expression: 'speaking', styleId: 'cozmo', family: 'calm' });
    run(supported, 20_000, values => {
      unsupported.step(16);
      expect(values.mouthOpen).toBe(unsupported.values().mouthOpen);
      expect(values.mouthSkew).toBe(unsupported.values().mouthSkew);
    });
  });

  it('keeps static and reduced-motion portraits at the original limb pose and resumes cleanly', () => {
    const rig = actor('oscar', 'speaking');
    run(rig, 600);
    rig.setReducedMotion(true);
    JOINTS.forEach(key => expect(rig.values()[key]).toBe(0));
    expect(rig.step(10_000)).toBe(false);
    rig.setReducedMotion(false);
    run(rig, 800);
    expect(Math.max(...ARMS.map(key => Math.abs(rig.values()[key])))).toBeGreaterThan(3);
  });

  it('does not accumulate offsets on the idle fast path across twenty thousand frames', () => {
    const small = actor();
    const large = actor();
    small.settle();
    large.settle();
    for (let index = 0; index < 20_000; index += 1) small.step(16);
    large.step(320_000);
    JOINTS.forEach(key => {
      expect(small.values()[key]).toBeCloseTo(large.values()[key], 8);
      expect(Math.abs(small.values()[key])).toBeLessThan(5);
    });
  });
});
