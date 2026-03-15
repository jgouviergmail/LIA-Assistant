/**
 * Hook for fetching app-level configuration from the backend.
 *
 * Fetches `/api/v1/config` which returns feature flags, rate limits,
 * i18n settings, etc. The result is cached for the lifetime of the component.
 *
 * Phase: evolution F4 — File Attachments & Vision Analysis
 * Created: 2026-03-09
 */

import { useApiQuery } from '@/hooks/useApiQuery';

/** Shape of the backend `/api/v1/config` response. */
export interface AppConfig {
  sse: {
    heartbeat_interval_seconds: number;
  };
  rate_limits: {
    enabled: boolean;
    per_minute: number;
    burst: number;
  };
  i18n: {
    supported_languages: string[];
    default_language: string;
  };
  features: {
    tool_approval_enabled: boolean;
    attachments_enabled: boolean;
    rag_spaces_enabled: boolean;
    rag_spaces_embedding_model: string;
  };
  api_version: string;
}

/**
 * Fetch the application configuration from the backend.
 *
 * @param enabled - Whether to fetch (default: true). Pass false to skip.
 * @returns `{ config, loading, error }`
 */
export function useAppConfig(enabled = true) {
  const { data, loading, error } = useApiQuery<AppConfig>(
    '/config',
    {
      componentName: 'useAppConfig',
      enabled,
    },
  );

  return { config: data ?? null, loading, error };
}
