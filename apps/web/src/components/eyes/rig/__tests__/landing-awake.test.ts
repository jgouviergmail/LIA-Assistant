import { describe, expect, it } from 'vitest';
import { pickActingSketch, resolveActingProfile } from '../acting-profile';
import { createEyeRig } from '../runtime';
import { createSketchClock, SKETCHES, type SketchName } from '../sketches';

const SLEEP_SCENES = ['doze-and-snap', 'body-doze', 'yawn-stretch'] as const;

describe('the landing rig stays awake without losing its comic life', () => {
  it.each(SLEEP_SCENES)('declines the explicit sleep performance %s', name => {
    const rig = createEyeRig({ characterId: 'bip', allowSleep: false });
    rig.playScene(name);
    expect(rig.isPerforming()).toBe(false);
    expect(rig.sketchClock().played).toBe(0);
    expect(rig.sketchClock().scene).toBeNull();
  });

  it.each(SLEEP_SCENES)('keeps %s available to the application by default', name => {
    const rig = createEyeRig({ characterId: 'bip' });
    rig.playScene(name);
    expect(rig.isPerforming()).toBe(true);
    expect(rig.sketchClock().scene).toBe(name);
  });

  it('still performs an actual hop with the awake restriction', () => {
    const rig = createEyeRig({ characterId: 'bip', allowSleep: false });
    rig.playScene('body-hops');
    expect(rig.isPerforming()).toBe(true);
    let highest = 0;
    for (let frame = 0; frame < 150; frame += 1) {
      rig.step(16);
      highest = Math.min(highest, rig.values().bodyY);
    }
    expect(highest).toBeLessThan(-0.08);
    expect(rig.sketchClock().scene).toBe('body-hops');
  });

  it('excludes sleep even from automatic scenes drawn at rest', () => {
    const seen = new Set<SketchName>();
    for (let draw = 0; draw <= 100; draw += 1) {
      const clock = createSketchClock();
      clock.dueMs = 1;
      const rig = createEyeRig({
        characterId: 'bip',
        allowSleep: false,
        lifeRandom: () => draw / 100,
        sketchClock: clock,
      });
      rig.step(16);
      expect(rig.isPerforming()).toBe(true);
      expect(clock.scene).not.toBeNull();
      expect(SLEEP_SCENES).not.toContain(clock.scene);
      if (clock.scene) seen.add(clock.scene);
    }
    expect(seen).toContain('body-hops');
    expect(seen).toContain('body-roll');
    expect(seen).toContain('fly');
  });

  it.each(['bip', 'moss'] as const)(
    'keeps every awake scene reachable for %s, including after exhausted history',
    identity => {
      const profile = resolveActingProfile(identity, 'cozmo');
      const awake = [
        'fly',
        'double-take',
        'sneeze',
        'hiccups',
        'peekaboo',
        'dizzy',
        'brow-groove',
        'suspicious',
        'body-hops',
        'body-roll',
        'body-somersault',
        'body-sneeze',
        'body-balloon',
        'body-jig',
        'body-startle',
        'body-bow',
      ];
      for (const recent of [[], SKETCHES]) {
        const seen = new Set(
          Array.from({ length: 1000 }, (_, draw) =>
            pickActingSketch(profile, () => draw / 1000, recent, false)
          )
        );
        expect(seen).toEqual(new Set(awake));
      }
    }
  );
});
