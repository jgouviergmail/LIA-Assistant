/**
 * A skill's life as the settings say it (lot 14): how often it was used since
 * counting began, whether it is proposed for switching off, and its way back.
 *
 * The verdicts are the server's (`dormant`, `previous_version_at`): this module
 * only words them. A count always states when counting began — nothing before
 * the migration was counted, so « never used » would be a guess.
 */

import type { Skill } from '@/hooks/useSkills';
import type { Language } from '@/i18n/settings';
import { formatDate } from '@/lib/format';

/** The settings' `t`, with the numeric `count` i18next pluralises on. */
export type SkillLifeTranslator = (
  key: string,
  options?: Record<string, string | number>
) => string;

/**
 * The skills the settings propose to switch off.
 *
 * Args:
 *   skills: The listed skills.
 *
 * Returns:
 *   The ones the server found dormant, still on, and nameable in an answer.
 */
export function dormantSkills(skills: readonly Skill[]): Skill[] {
  return skills.filter(
    skill => skill.dormant === true && skill.enabled_for_user && Boolean(skill.skill_id)
  );
}

/** A calendar day in the reader's language. */
export function skillLifeDay(iso: string, lng: Language): string {
  return formatDate(iso, lng, { dateStyle: 'medium' });
}

/**
 * The line under a skill saying how often it was used.
 *
 * Args:
 *   skill: The listed skill.
 *   t: The translator.
 *   lng: The reader's language.
 *
 * Returns:
 *   The worded line, or null when its use cannot be observed (always loaded:
 *   it enters every message with nothing to count) or the API predates it.
 */
export function skillUsageLine(skill: Skill, t: SkillLifeTranslator, lng: Language): string | null {
  if (skill.always_loaded || !skill.counted_since || skill.use_count === undefined) return null;
  const since = skillLifeDay(skill.counted_since, lng);
  if (skill.use_count === 0 || !skill.last_used_at) {
    return t('settings.skills.usage.none', { since });
  }
  return t('settings.skills.usage.used', {
    count: skill.use_count,
    since,
    last: skillLifeDay(skill.last_used_at, lng),
  });
}
