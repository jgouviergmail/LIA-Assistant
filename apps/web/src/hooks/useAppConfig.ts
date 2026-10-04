/**
 * Hook for fetching app-level configuration from the backend.
 *
 * Fetches `/api/v1/config` which returns feature flags, rate limits,
 * i18n settings, etc. The endpoint is public: a reader never needs to wait for
 * the session to ask.
 *
 * A component starts from the dashboard layout's last read when it is mounted
 * under it (`AppConfigSeedContext`), then reads its own: a page reached by a
 * navigation renders its gated parts at once — the home page's radio card used
 * to land a round trip after the page and push « My dashboard » down — and is
 * never staler than its own read.
 *
 * Phase: evolution F4 — File Attachments & Vision Analysis
 * Created: 2026-03-09
 */

import { createContext, useContext } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';

/** Shape of the backend `/api/v1/config` response. */
export interface AppConfig {
  route_maps?: { enabled: boolean; estimated_cost_eur?: string };
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
    interactive_route_maps_enabled?: boolean;
    tool_approval_enabled: boolean;
    attachments_enabled: boolean;
    rag_spaces_enabled: boolean;
    rag_spaces_embedding_model: string;
    // Mail source (ADR-262) — gates the « Gmail labels » section of a space.
    rag_spaces_mail_sync_enabled?: boolean;
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
    // The workboard (ADR-276) — gates its settings section, its hub section and
    // the board page itself. Published by the API since lot 1.
    workboard_enabled?: boolean;
    // Message bookmarks (ADR-282) — gates the bubble toggle and the « Bookmarks » tab.
    bookmarks_enabled?: boolean;
    // Sandbox egress (ADR-298) — gates the « Sandbox network » settings section.
    python_sandbox_egress_enabled?: boolean;
    // Live voice mode (ADR-299) — gates the Live button, the « Live mode »
    // settings section and the Live connector group.
    live_enabled?: boolean;
    // Sending by e-mail (ADR-321) — the deployment ceiling of every « Send by
    // e-mail » action; the effective state is `capabilities.email_share`.
    email_share_enabled?: boolean;
    // Personal radio (ADR-324) — the deployment ceiling of the player, the radio
    // page and its settings; the effective state is `capabilities.radio`.
    radio_enabled?: boolean;
    // Skill library (ADR-327) — the deployment ceiling of « Find skills »; the
    // effective state is `capabilities.skill_library` (with `capabilities.skills`).
    skill_library_enabled?: boolean;
  };
  // Every capability of the registry with its EFFECTIVE state (deployment
  // ceiling AND operator switch), keyed like `capabilities.items.<key>`.
  // Read server-side by the instance that advertises this one as its
  // demonstrator (`product/demo_capabilities.py`) and relayed to its
  // landing; optional here because an older API omits it.
  capabilities?: Record<string, { enabled: boolean; family: string }>;
  api_version: string;
}

/** The dashboard layout's last read of the configuration, the one its pages start from. */
export const AppConfigSeedContext = createContext<AppConfig | null>(null);

/**
 * Fetch the application configuration from the backend.
 *
 * @param enabled - Whether to fetch (default: true). Pass false to skip.
 * @returns `{ config, loading, error }`
 */
export function useAppConfig(enabled = true) {
  const seed = useContext(AppConfigSeedContext);
  const { data, loading, error } = useApiQuery<AppConfig>('/config', {
    componentName: 'useAppConfig',
    enabled,
    initialData: seed ?? undefined,
  });

  return { config: data ?? null, loading, error };
}
