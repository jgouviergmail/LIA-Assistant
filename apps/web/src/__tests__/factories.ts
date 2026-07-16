/**
 * Shared, contract-conformant test data factories.
 *
 * Every factory takes `Partial<T>` overrides and returns a fully-typed `T`, so
 * a typo'd or wrongly-typed override is a compile error — never an `as never`
 * / `as any` / `Record<string, unknown>` escape hatch (see the frontend audit
 * F057 rule: builders must honour the public contract). Add a domain factory
 * here the moment a second test needs the same shape.
 */

import type { User } from '@/lib/auth';
import type { Connector } from '@/components/settings/connectors/types';

/**
 * A fully-populated, authenticated {@link User}. Required fields carry neutral
 * defaults; pass `over` to steer the fields a given test asserts on.
 */
export function makeUser(over: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'user@test.dev',
    is_active: true,
    is_verified: true,
    is_superuser: false,
    memory_enabled: true,
    execution_mode: 'pipeline',
    voice_enabled: false,
    voice_mode_enabled: false,
    voice_stt_mode: 'local',
    tokens_display_enabled: false,
    debug_panel_enabled: false,
    response_display_mode: 'default',
    onboarding_completed: true,
    ...over,
  };
}

/**
 * A connected {@link Connector} row (calendar by default). Override
 * `connector_type`/`status` to exercise the available/connected/error cards.
 */
export function makeConnector(over: Partial<Connector> = {}): Connector {
  return {
    id: 'c1',
    connector_type: 'google_calendar',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}
