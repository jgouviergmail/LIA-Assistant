import type { AppConfig } from '@/hooks/useAppConfig';

type Overrides = Omit<Partial<AppConfig>, 'features'> & {
  features?: Partial<AppConfig['features']>;
};

/** A complete wire contract; individual tests opt into their capabilities. */
export function appConfigFixture(overrides: Overrides = {}): AppConfig {
  return {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['en'], default_language: 'en' },
    api_version: 'v1',
    ...overrides,
    features: {
      tool_approval_enabled: true,
      attachments_enabled: true,
      rag_spaces_enabled: false,
      rag_spaces_embedding_model: '',
      journals_enabled: false,
      ...overrides.features,
    },
  };
}
