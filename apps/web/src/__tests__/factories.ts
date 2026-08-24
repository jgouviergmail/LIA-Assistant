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
