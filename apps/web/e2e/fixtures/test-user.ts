/**
 * Deterministic User payload for the hermetic auth mock (audit F031).
 *
 * Mirrors the `User` interface consumed by the app's AuthProvider
 * (`src/lib/auth.tsx`). Kept intentionally minimal-but-complete: every field
 * the provider or a smoke-covered page reads must be present, so the app never
 * falls back to a loading/redirect state for a reason unrelated to the test.
 */
export interface TestUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  memory_enabled: boolean;
  execution_mode: string;
  /** Effective exchange rhythm the API publishes (ADR-311). */
  exchange_rhythm: 'frequent' | 'occasional';
  voice_enabled: boolean;
  speaking_avatar_enabled: boolean;
  voice_mode_enabled: boolean;
  voice_stt_mode: 'local' | 'remote';
  tokens_display_enabled: boolean;
  debug_panel_enabled: boolean;
  response_display_mode: string;
  onboarding_completed: boolean;
  language: string;
  timezone: string;
  /** Settings section tokens pinned to the floating dock (ADR-277). */
  settings_shortcuts: string[];
  /** Interface text size in px; the account's copy is applied on every page. */
  font_size: number;
}

export function makeTestUser(overrides: Partial<TestUser> = {}): TestUser {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    email: 'e2e.user@example.test',
    full_name: 'E2E User',
    is_active: true,
    is_verified: true,
    is_superuser: false,
    memory_enabled: true,
    execution_mode: 'pipeline',
    exchange_rhythm: 'occasional',
    voice_enabled: false,
    speaking_avatar_enabled: false,
    voice_mode_enabled: false,
    voice_stt_mode: 'remote',
    tokens_display_enabled: true,
    settings_shortcuts: [],
    font_size: 16,
    debug_panel_enabled: false,
    response_display_mode: 'default',
    onboarding_completed: true,
    language: 'en',
    timezone: 'UTC',
    ...overrides,
  };
}
