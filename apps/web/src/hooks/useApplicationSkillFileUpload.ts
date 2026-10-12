'use client';

import {
  useApplicationFileUpload,
  type FileUploadDefinition,
} from '@/hooks/useApplicationFileUpload';
import {
  skillFileUploadResultSchema,
  skillFileUploadSelectionSchema,
  type SkillFileUploadSelection,
} from '@/lib/application-skill-file-upload';
import { apiEndpointUrl } from '@/lib/api-client';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const definition: FileUploadDefinition<SkillFileUploadSelection> = {
  operationId: 'skill_file.upload',
  resource: 'skills',
  select(status) {
    const parsed = skillFileUploadSelectionSchema.safeParse(
      status.outcome?.values.skill_file_upload ?? status.prior_outcome?.values.skill_file_upload
    );
    return parsed.success ? parsed.data : null;
  },
  endpoint: commandId => apiEndpointUrl(`/application-commands/${commandId}/skill-upload`),
  accept(value, _commandId, selection) {
    const result = skillFileUploadResultSchema.safeParse(value);
    if (!result.success) return null;
    const imported = result.data.values.skill_file_upload;
    if (
      selection.previous &&
      (imported.skill_id !== selection.previous.skill_id ||
        imported.name !== selection.previous.name)
    )
      return null;
    return { cacheRefreshPending: result.data.values.cache_refresh_pending };
  },
};

export function useApplicationSkillFileUpload(
  status: ApplicationCommandStatus,
  checkResult: () => Promise<void>
) {
  return useApplicationFileUpload(status, checkResult, definition);
}
