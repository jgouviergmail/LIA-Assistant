/** The same published capability seed the dashboard provides to its card children. */
import type { ReactNode } from 'react';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';

export function cardToolsConfig(enabled: boolean): AppConfig {
  return {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['en', 'fr'], default_language: 'fr' },
    features: {
      tool_approval_enabled: false,
      attachments_enabled: true,
      rag_spaces_enabled: false,
      rag_spaces_embedding_model: 'none',
      journals_enabled: false,
      workbench_enabled: enabled,
    },
    capabilities: { workbench: { enabled, family: 'work' } },
    api_version: 'v1',
  };
}
const enabled = cardToolsConfig(true);
export function CardToolsAvailable({ children }: { children: ReactNode }) {
  return <AppConfigSeedContext.Provider value={enabled}>{children}</AppConfigSeedContext.Provider>;
}
