'use client';

import {
  useApplicationFileUpload,
  type FileUploadDefinition,
} from '@/hooks/useApplicationFileUpload';
import {
  pluginFileUploadResultSchema,
  pluginFileUploadSelectionSchema,
  type PluginFileUploadSelection,
} from '@/lib/application-plugin-file-upload';
import { apiEndpointUrl } from '@/lib/api-client';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const definition: FileUploadDefinition<PluginFileUploadSelection> = {
  operationId: 'plugin_file.upload',
  resource: 'plugins',
  resources: ['plugins', 'skills', 'user_mcp'],
  select(status) {
    const result = pluginFileUploadSelectionSchema.safeParse(
      status.outcome?.values.plugin_file_upload ?? status.prior_outcome?.values.plugin_file_upload
    );
    return result.success ? result.data : null;
  },
  endpoint: commandId => apiEndpointUrl(`/application-commands/${commandId}/plugin-upload`),
  accept(value, _commandId, selection) {
    const result = pluginFileUploadResultSchema.safeParse(value);
    if (!result.success) return null;
    const imported = result.data.values.plugin_file_upload;
    if (
      selection.previous &&
      (imported.plugin_id !== selection.previous.id || imported.name !== selection.previous.name)
    )
      return null;
    return {
      cacheRefreshPending: result.data.values.cache_refresh_pending,
      details: result.data.values,
    };
  },
};

export function useApplicationPluginFileUpload(
  status: ApplicationCommandStatus,
  checkResult: () => Promise<void>
) {
  return useApplicationFileUpload(status, checkResult, definition);
}
