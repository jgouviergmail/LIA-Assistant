/**
 * Hook for managing LLM configuration admin state.
 * Provides queries for configs/providers/metadata and mutations for updates.
 */

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import type {
  LLMConfigListResponse,
  LLMTypeConfig,
  LLMTypeConfigUpdate,
  ProviderKeysResponse,
  ProviderModelsMetadata,
} from '@/types/llm-config';

const COMPONENT_NAME = 'AdminLLMConfigSection';

export function useLLMConfig() {
  const {
    data: configsData,
    loading: configsLoading,
    refetch: refetchConfigs,
  } = useApiQuery<LLMConfigListResponse>('/admin/llm-config/types', {
    componentName: COMPONENT_NAME,
    initialData: { configs: [] },
  });

  const {
    data: providersData,
    loading: providersLoading,
    refetch: refetchProviders,
  } = useApiQuery<ProviderKeysResponse>('/admin/llm-config/providers', {
    componentName: COMPONENT_NAME,
    initialData: { providers: [] },
  });

  const { data: metadata, loading: metadataLoading } = useApiQuery<ProviderModelsMetadata>(
    '/admin/llm-config/metadata/models',
    {
      componentName: COMPONENT_NAME,
      initialData: { providers: {} },
    }
  );

  const { mutate: updateConfigMutate, loading: updatingConfig } = useApiMutation<
    LLMTypeConfigUpdate,
    LLMTypeConfig
  >({
    method: 'PUT',
    componentName: COMPONENT_NAME,
  });

  const { mutate: resetConfigMutate, loading: resettingConfig } = useApiMutation<
    void,
    LLMTypeConfig
  >({
    method: 'POST',
    componentName: COMPONENT_NAME,
  });

  const { mutate: updateKeyMutate, loading: updatingKey } = useApiMutation({
    method: 'PUT',
    componentName: COMPONENT_NAME,
  });

  const { mutate: deleteKeyMutate, loading: deletingKey } = useApiMutation({
    method: 'DELETE',
    componentName: COMPONENT_NAME,
  });

  const updateConfig = async (llmType: string, data: LLMTypeConfigUpdate) => {
    const result = await updateConfigMutate(`/admin/llm-config/types/${llmType}`, data);
    await refetchConfigs();
    return result;
  };

  const resetConfig = async (llmType: string) => {
    const result = await resetConfigMutate(`/admin/llm-config/types/${llmType}/reset`);
    await refetchConfigs();
    return result;
  };

  const updateProviderKey = async (provider: string, key: string) => {
    await updateKeyMutate(`/admin/llm-config/providers/${provider}`, { key });
    await refetchProviders();
  };

  const deleteProviderKey = async (provider: string) => {
    await deleteKeyMutate(`/admin/llm-config/providers/${provider}`);
    await refetchProviders();
  };

  return {
    configs: configsData?.configs ?? [],
    providers: providersData?.providers ?? [],
    metadata: metadata ?? { providers: {} },
    loading: configsLoading || providersLoading || metadataLoading,
    updatingConfig: updatingConfig || resettingConfig,
    updatingKey: updatingKey || deletingKey,
    updateConfig,
    resetConfig,
    updateProviderKey,
    deleteProviderKey,
    refetchConfigs,
    refetchProviders,
  };
}
