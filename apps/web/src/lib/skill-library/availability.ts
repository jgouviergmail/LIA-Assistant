/**
 * Whether the skill library is offered on this instance — the EFFECTIVE state (ADR-327).
 *
 * A library skill is a skill: the library needs BOTH capabilities, each read
 * from the capability map (deployment ceiling AND operator switch). An older
 * API that omits the map falls back to the two deployment flags.
 */
import type { AppConfig } from '@/hooks/useAppConfig';

/** The part of the app configuration the availability reads. */
export interface SkillLibraryConfig {
  features?: { skills_enabled?: boolean; skill_library_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

function enabled(config: SkillLibraryConfig, key: 'skills' | 'skill_library'): boolean {
  const capability = config.capabilities?.[key];
  if (capability) return capability.enabled;
  return Boolean(config.features?.[key === 'skills' ? 'skills_enabled' : 'skill_library_enabled']);
}

/**
 * @param config - The app configuration, or null while it loads.
 * @returns True when « Find skills » leads somewhere.
 */
export function skillLibraryAvailable(config: SkillLibraryConfig | null): boolean {
  return config !== null && enabled(config, 'skills') && enabled(config, 'skill_library');
}
