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
  voice_enabled: boolean;
  voice_mode_enabled: boolean;
  voice_stt_mode: 'local' | 'remote';
  tokens_display_enabled: boolean;
  debug_panel_enabled: boolean;
  response_display_mode: string;
  onboarding_completed: boolean;
  language: string;
  timezone: string;
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
    voice_enabled: false,
    voice_mode_enabled: false,
    voice_stt_mode: 'remote',
    tokens_display_enabled: true,
    debug_panel_enabled: false,
    response_display_mode: 'default',
    onboarding_completed: true,
    language: 'en',
    timezone: 'UTC',
    ...overrides,
  };
}
