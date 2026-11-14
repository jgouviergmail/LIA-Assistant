/**
 * Whether the skill library is offered on this instance — the EFFECTIVE state (ADR-327).
 *
 * A library skill is a skill: the library needs BOTH capabilities, each read
 * from the capability map (deployment ceiling AND operator switch). An older
 * API that omits the map falls back to the two deployment flags.
 *
 * The skills are a capability of the common door (their settings sections ask
 * it too); the library's own half is read here.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityAvailable } from '@/lib/capability-availability';
import { capabilityEnabled } from '@/lib/capability-state';

/** The part of the app configuration the availability reads. */
export interface SkillLibraryConfig {
  features?: { skills_enabled?: boolean; skill_library_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration, or null while it loads.
 * @returns True when « Find skills » leads somewhere.
 */
export function skillLibraryAvailable(config: SkillLibraryConfig | null): boolean {
  return (
    config !== null &&
    capabilityAvailable(config, 'skills') &&
    capabilityEnabled(config.capabilities, 'skill_library', config.features?.skill_library_enabled)
  );
}
