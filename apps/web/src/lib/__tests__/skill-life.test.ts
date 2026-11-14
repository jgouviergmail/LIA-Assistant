/**
 * A skill's life as the settings say it (lot 14): which skills are proposed
 * for switching off, and the usage line under each one.
 */

import { describe, expect, it } from 'vitest';

import type { Skill } from '@/hooks/useSkills';
import { formatDate } from '@/lib/format';
import { dormantSkills, skillUsageLine, type SkillLifeTranslator } from '@/lib/skill-life';

function skill(over: Partial<Skill> = {}): Skill {
  return {
    name: 'notes',
    description: 'Notes.',
    descriptions: null,
    scope: 'user',
    category: null,
    priority: 50,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    skill_id: 'skill-notes',
    use_count: 0,
    last_used_at: null,
    counted_since: '2026-11-13T09:00:00Z',
    dormant: false,
    previous_version_at: null,
    ...over,
  };
}

/** Echoes the key and its options, so the test reads what was asked. */
const t: SkillLifeTranslator = (key, options) => `${key} ${JSON.stringify(options ?? {})}`;
const day = (iso: string) => formatDate(iso, 'en', { dateStyle: 'medium' });

describe('dormantSkills', () => {
  it('proposes only the skills the server found dormant and that are still on', () => {
    const idle = skill({ name: 'idle', skill_id: 'skill-idle', dormant: true });
    const off = skill({
      name: 'off',
      skill_id: 'skill-off',
      dormant: true,
      enabled_for_user: false,
    });
    const busy = skill({ name: 'busy', skill_id: 'skill-busy', dormant: false });

    expect(dormantSkills([idle, off, busy]).map(s => s.name)).toEqual(['idle']);
  });

  it('never proposes a skill it cannot name to the server', () => {
    expect(dormantSkills([skill({ dormant: true, skill_id: null })])).toEqual([]);
  });
});

describe('skillUsageLine', () => {
  it('states the count with the day counting began and the last use', () => {
    const line = skillUsageLine(
      skill({ use_count: 3, last_used_at: '2026-12-02T10:00:00Z' }),
      t,
      'en'
    );

    expect(line).toBe(
      `settings.skills.usage.used ${JSON.stringify({
        count: 3,
        since: day('2026-11-13T09:00:00Z'),
        last: day('2026-12-02T10:00:00Z'),
      })}`
    );
  });

  it('says no use was recorded since counting began, never « never used »', () => {
    expect(skillUsageLine(skill(), t, 'en')).toBe(
      `settings.skills.usage.none ${JSON.stringify({ since: day('2026-11-13T09:00:00Z') })}`
    );
  });

  it('says nothing of a skill whose use cannot be observed, or of an older answer', () => {
    expect(skillUsageLine(skill({ always_loaded: true, use_count: 2 }), t, 'en')).toBeNull();
    expect(skillUsageLine(skill({ counted_since: undefined }), t, 'en')).toBeNull();
  });
});
