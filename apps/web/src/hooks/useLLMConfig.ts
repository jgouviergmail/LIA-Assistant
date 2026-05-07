/**
 * Hook for managing LLM configuration admin state.
 * Provides queries for configs/providers/metadata and mutations for updates.
 */

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useCatalogueInvalidationListener } from '@/lib/catalogue-invalidation-context';
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

  const {
    data: metadata,
    loading: metadataLoading,
    refetch: refetchMetadata,
  } = useApiQuery<ProviderModelsMetadata>(
    // The Configuration LLM admin edits chat + image + audio + tts LLM
    // types. ``audio`` covers voice_transcription (STT, ElevenLabs Scribe).
    // ``tts`` covers the voice_tts type added in v1.20.x for voice synthesis
    // (Edge / OpenAI / ElevenLabs). Without it, kind=tts providers would be
    // filtered out at the API and never appear in the Provider selector.
    // Per-type fine-grained filtering happens client-side via
    // LLMTypeInfo.required_kind.
    '/admin/llm-config/metadata/models?kinds=chat,image,audio,tts',
    {
      componentName: COMPONENT_NAME,
      initialData: { providers: {} },
    }
  );

  // Refetch metadata when a sibling Tarification pane mutates the catalogue
  // (chat models or image-generation models). Mirrors the backend's ADR-063
  // cache-name based invalidation, but cross-component instead of cross-worker.
  useCatalogueInvalidationListener('model_capabilities', refetchMetadata);
  useCatalogueInvalidationListener('image_generation_options', refetchMetadata);

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
