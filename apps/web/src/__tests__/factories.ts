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
import type { AdminUserUsageLimitResponse } from '@/types/usage-limits';
import type { LLMModelPricing } from '@/components/settings/AdminLLMPricingSection';
import type { Message, MessageAttachmentMeta } from '@/types/chat';
import type { ScheduledAction } from '@/hooks/useScheduledActions';

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

/**
 * An LLM model pricing row (`/admin/llm/pricing`). A plain chat model with no
 * reasoning widget; override the dimension under test.
 *
 * Note: `effective_from` and `is_active` are part of the contract and are set
 * here — the previous inline fixture omitted them and papered over it with an
 * `as LLMModelPricing` cast.
 */
export function makeLLMPricing(over: Partial<LLMModelPricing> = {}): LLMModelPricing {
  return {
    id: 'm1',
    provider: 'anthropic',
    model_name: 'claude-x',
    kind: 'chat',
    capability_provenance: 'imported',
    deprecation_date: null,
    max_input_tokens: 200000,
    max_output_tokens: 8192,
    supports_tools: true,
    supports_structured_output: true,
    supports_strict_mode: false,
    supports_streaming: true,
    supports_vision: true,
    is_reasoning_model: false,
    reasoning_enum_values: null,
    reasoning_doc_i18n_key: null,
    supports_temperature: true,
    supports_top_p: true,
    supports_frequency_penalty: true,
    supports_presence_penalty: true,
    pricing_unit: 'per_1m_tokens',
    input_unit_price: '3.0',
    cached_input_unit_price: '0.3',
    output_unit_price: '15.0',
    time_slots: null,
    effective_from: '2026-01-01T00:00:00Z',
    is_active: true,
    ...over,
  };
}

/**
 * An admin usage-limits row (`/usage-limits/admin/users`). Every limit is
 * unlimited and every counter at zero by default — override the dimension the
 * test is about.
 */
export function makeUsageLimitsUser(
  over: Partial<AdminUserUsageLimitResponse> = {}
): AdminUserUsageLimitResponse {
  return {
    user_id: 'u1',
    email: 'a@b.co',
    full_name: null,
    is_active: true,
    is_usage_blocked: false,
    blocked_reason: null,
    blocked_at: null,
    blocked_by: null,
    token_limit_per_cycle: 1000,
    message_limit_per_cycle: 50,
    cost_limit_per_cycle: 5,
    token_limit_absolute: null,
    message_limit_absolute: null,
    cost_limit_absolute: null,
    cycle_tokens: 0,
    cycle_messages: 0,
    cycle_cost: 0,
    total_tokens: 0,
    total_messages: 0,
    total_cost: 0,
    status: 'ok',
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/**
 * A chat {@link Message}. Only four fields are required by the contract, but
 * going through the factory keeps fixtures free of the `as Message` assertion
 * that a bare literal needs to pin `role` to its union member.
 */
export function makeMessage(over: Partial<Message> = {}): Message {
  return {
    id: 'm-1',
    role: 'assistant',
    content: 'Hello world',
    timestamp: new Date('2026-07-19T10:00:00Z'),
    ...over,
  };
}

/** An image {@link MessageAttachmentMeta} carried by a user message. */
export function makeAttachment(over: Partial<MessageAttachmentMeta> = {}): MessageAttachmentMeta {
  return {
    id: 'att-1',
    filename: 'photo.png',
    mime_type: 'image/png',
    size: 2048,
    content_type: 'image',
    ...over,
  };
}

/**
 * A weekly routine, contract-conformant.
 *
 * Four test files carried their own copy of this shape and all four broke the
 * day the API dropped `days_of_week` — while staying green, because a fabricated
 * payload cannot notice a contract change (that is what
 * `test_frontend_contract_guard.py` now catches on the backend side). One
 * factory, so the next contract move is one edit.
 *
 * `times_of_day`, `runs_per_day` and `week_slots` are what the SERVER
 * materialises; a test that omits them is testing a payload the API never
 * sends.
 */
export function makeScheduledAction(over: Partial<ScheduledAction> = {}): ScheduledAction {
  return {
    id: 'r',
    user_id: 'u1',
    title: 'Routine',
    action_prompt: 'do',
    recurrence: {
      freq: 'weekly',
      interval: 1,
      anchor_date: '2026-01-05',
      byweekday: [1],
      bymonthday: [],
      bymonth: [],
      nth_weekday: null,
      times: { mode: 'at', at: [{ hour: 8, minute: 0 }] },
      end: { kind: 'never', on_date: null, after_count: null },
    },
    user_timezone: 'Europe/Paris',
    trigger_kind: 'time',
    condition_config: null,
    requires_approval: false,
    execution_mode: 'react',
    next_trigger_at: '2026-08-03T06:00:00Z',
    is_enabled: true,
    status: 'active',
    last_executed_at: null,
    execution_count: 0,
    consecutive_failures: 0,
    last_error: null,
    schedule_display: 'Mon 08:00',
    times_of_day: ['08:00'],
    runs_per_day: 1,
    week_slots: [
      {
        day: 1,
        date: '2026-08-03',
        slot_at: '2026-08-03T06:00:00Z',
        hour: 8,
        minute: 0,
      },
    ],
    next_occurrences: ['2026-08-03T06:00:00Z'],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/**
 * A routine firing at several moments of one day.
 *
 * The shape the previous grid could not draw: keyed by `(routine, day)` it
 * produced one chip carrying the FIRST moment's state, and the second
 * occurrence — including its failure — was invisible.
 */
export function makeMultiSlotAction(over: Partial<ScheduledAction> = {}): ScheduledAction {
  return makeScheduledAction({
    times_of_day: ['08:00', '18:00'],
    runs_per_day: 2,
    recurrence: {
      freq: 'weekly',
      interval: 1,
      anchor_date: '2026-01-05',
      byweekday: [1],
      bymonthday: [],
      bymonth: [],
      nth_weekday: null,
      times: {
        mode: 'at',
        at: [
          { hour: 8, minute: 0 },
          { hour: 18, minute: 0 },
        ],
      },
      end: { kind: 'never', on_date: null, after_count: null },
    },
    week_slots: [
      { day: 1, date: '2026-08-03', slot_at: '2026-08-03T06:00:00Z', hour: 8, minute: 0 },
      { day: 1, date: '2026-08-03', slot_at: '2026-08-03T16:00:00Z', hour: 18, minute: 0 },
    ],
    ...over,
  });
}
