/**
 * « Find skills » leads somewhere only when BOTH switches are on (ADR-327):
 * a library skill is a skill.
 */
import { describe, expect, it } from 'vitest';

import { skillLibraryAvailable } from '../availability';

const on = { enabled: true, family: 'reach' };
const off = { enabled: false, family: 'reach' };

describe('the skill library is offered', () => {
  it('when the capability map says both are on', () => {
    expect(skillLibraryAvailable({ capabilities: { skills: on, skill_library: on } })).toBe(true);
  });

  it.each([[{ skills: off, skill_library: on }], [{ skills: on, skill_library: off }]])(
    'never when either is off (%o)',
    capabilities => {
      expect(skillLibraryAvailable({ capabilities })).toBe(false);
    }
  );

  it('from the deployment flags on an older API without the map', () => {
    expect(
      skillLibraryAvailable({ features: { skills_enabled: true, skill_library_enabled: true } })
    ).toBe(true);
    expect(skillLibraryAvailable({ features: { skills_enabled: true } })).toBe(false);
  });

  it('never while the configuration loads', () => {
    expect(skillLibraryAvailable(null)).toBe(false);
  });
});
