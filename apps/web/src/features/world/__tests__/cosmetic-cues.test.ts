import { expect, it } from 'vitest';
import { WORLD } from '../definition';
import { cosmeticCue } from '../audio/cosmetic-cues';
it('assigns a distinct local sound to every authored machine and refuses unknown machine identities', () => {
  const machines = WORLD.props.filter(prop => prop.kind === 'machine');
  expect(machines).toHaveLength(3);
  const cues = machines.map(prop => cosmeticCue('machine', prop.id));
  expect(cues).not.toContain(null);
  expect(new Set(cues).size).toBe(3);
  expect(cosmeticCue('machine', 'unknown')).toBeNull();
  expect(cosmeticCue('machine', '__proto__')).toBeNull();
  expect(cosmeticCue('plant')).toBe('leaves');
});
