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
    journals_enabled: boolean;
    // UXR Lot 6 (A10) — additive instance flags (gate-keeper ADR-061).
    channels_enabled?: boolean;
    heartbeat_enabled?: boolean;
    skills_enabled?: boolean;
    open_loops_enabled?: boolean;
    // Habits program (ADR-214) — gates the « Habitudes » settings section.
    habits_enabled?: boolean;
    // Peers program — gates the « Connexions » settings section.
    peers_enabled?: boolean;
    // Activity timeline (Lot 1-A1) — gates its entry links.
    activity_timeline_enabled?: boolean;
    // Meeting recording & minutes (ADR-258) — gates the composer entry and the recorder.
    meetings_enabled?: boolean;
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
  const { data, loading, error } = useApiQuery<AppConfig>('/config', {
    componentName: 'useAppConfig',
    enabled,
  });

  return { config: data ?? null, loading, error };
}
