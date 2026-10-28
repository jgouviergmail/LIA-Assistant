'use client';

import {
  experienceViewSchema,
  type ExperienceView,
  type ExperienceWrite,
} from './experience-protocol';
import { useWorldOwnerPreferences } from './useWorldOwnerPreferences';

export type WorldExperienceControl = ReturnType<typeof useWorldExperiencePreferences>;
export function useWorldExperiencePreferences(ownerId: string, enabled: boolean) {
  const { value, save, ...state } = useWorldOwnerPreferences<ExperienceView, ExperienceWrite>(
    ownerId,
    enabled,
    'experience',
    experienceViewSchema
  );
  return {
    ...state,
    experience: value,
    save: async (payload: ExperienceWrite) => Boolean(await save(payload)),
  };
}
