import { describe, expect, it } from 'vitest';
import { pickIdleGesture } from '@/components/eyes/expression-engine';
import { resolveLoops } from '@/components/eyes/rig/poses';

describe('quiet presence', () => {
  it.each(['lively', 'calm', 'drowsy'] as const)(
    '%s keeps gaze and lids alive without choosing a decorative or conversational gesture',
    family => {
      const selected = new Set(
        Array.from({ length: 1000 }, (_, index) =>
          pickIdleGesture(() => (index + 0.5) / 1000, family)
        )
      );
      expect(selected).toContain('saccade');
      expect(selected).toContain('half-blink');
      for (const removed of [
        'swap',
        'bump',
        'spin',
        'jelly',
        'tilt',
        'bounce',
        'nod',
        'consider',
      ]) {
        expect(selected).not.toContain(removed);
      }
    }
  );

  it.each(['neutral', 'excited', 'speaking'] as const)(
    '%s breathes without continuously hopping or rotating its eyes',
    expression => {
      const loops = resolveLoops(expression, 'calm');
      expect(loops.some(loop => loop.channel === 'mass' && loop.amplitude > 0)).toBe(true);
      expect(loops.filter(loop => /^(ty|sy|rot)[LR]$/.test(loop.channel))).toEqual([]);
    }
  );
});
