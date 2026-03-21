/**
 * Usage limits types for per-user resource management.
 *
 * Matches backend schemas from src/domains/usage_limits/schemas.py.
 */

/** Usage limit enforcement status */
export type UsageLimitStatus = 'ok' | 'warning' | 'critical' | 'blocked_limit' | 'blocked_manual';

/** Single limit dimension with current usage and configured limit */
export interface LimitDetail {
  current: number;
  limit: number | null;
  usage_pct: number | null;
  exceeded: boolean;
}

/** User-facing usage limits response (GET /usage-limits/me) */
export interface UserUsageLimitResponse {
  status: UsageLimitStatus;
  is_blocked: boolean;
  blocked_reason: string | null;
  cycle_tokens: LimitDetail;
  cycle_messages: LimitDetail;
  cycle_cost: LimitDetail;
  absolute_tokens: LimitDetail;
  absolute_messages: LimitDetail;
  absolute_cost: LimitDetail;
  cycle_start: string;
  cycle_end: string;
}

/** Admin view: single user with limits and usage */
export interface AdminUserUsageLimitResponse {
  user_id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_usage_blocked: boolean;
  blocked_reason: string | null;
  blocked_at: string | null;
  blocked_by: string | null;
  token_limit_per_cycle: number | null;
  message_limit_per_cycle: number | null;
  cost_limit_per_cycle: number | null;
  token_limit_absolute: number | null;
  message_limit_absolute: number | null;
  cost_limit_absolute: number | null;
  cycle_tokens: number;
  cycle_messages: number;
  cycle_cost: number;
  total_tokens: number;
  total_messages: number;
  total_cost: number;
  status: UsageLimitStatus;
  created_at: string;
}

/** Paginated admin list response */
export interface AdminUsageLimitsListResponse {
  users: AdminUserUsageLimitResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Request payload for updating limits */
export interface UsageLimitUpdateRequest {
  token_limit_per_cycle?: number | null;
  message_limit_per_cycle?: number | null;
  cost_limit_per_cycle?: number | null;
  token_limit_absolute?: number | null;
  message_limit_absolute?: number | null;
  cost_limit_absolute?: number | null;
}

/** Request payload for block toggle */
export interface UsageBlockUpdateRequest {
  is_usage_blocked: boolean;
  blocked_reason?: string | null;
}

/** WebSocket stats update event */
export interface UsageStatsUpdateEvent {
  type: 'stats_update';
  data: AdminUserUsageLimitResponse[];
  total: number;
}
