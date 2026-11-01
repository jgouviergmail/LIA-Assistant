/**
 * What a personal MCP server will do, as the API states it (spec 2026-10-30).
 *
 * The page never decides a confirmation or a shape on its own: the API computes the
 * synthesis with the rules a run applies (`domains/user_mcp/behavior.py`) and
 * publishes the defaults a choice left open inherits. This module only names the
 * vocabulary and maps the page's choices to the stored values. Every vocabulary below mirrors a
 * backend enum (a backend test reads this file) and has a translation in six
 * languages (a frontend test reads the locales).
 */

/** What a choice left open inherits — `GET /mcp/servers` publishes it. */
export interface UserMCPDefaults {
  confirmation_instance: boolean;
  confirmation_account: boolean | null;
  confirmation_effective: boolean;
  react_direct_tools_default: boolean;
  dedicated_agents_available: boolean;
}

export const MCP_CONFIRMATION_REASONS = [
  'tool_always',
  'tool_never',
  'server_always',
  'account_always',
  'instance_always',
  'declared_destructive',
  'declared_modifying',
  'declared_additive',
  'declared_read_only',
  'not_declared',
] as const;
export type MCPConfirmationReason = (typeof MCP_CONFIRMATION_REASONS)[number];

/** A person's choice for one tool — the first level (spec 2026-10-30 D6). */
export const MCP_TOOL_CHOICES = ['always', 'never'] as const;
export type MCPToolChoice = (typeof MCP_TOOL_CHOICES)[number];

/** How a call LIA uses directly is asked; a dedicated agent is asked before its task. */
export const MCP_QUESTION_FLOWS = ['in_loop', 'card_after_task'] as const;
export type MCPQuestionFlow = (typeof MCP_QUESTION_FLOWS)[number];

export const MCP_BEHAVIOR_NOTES = [
  'tools_unknown',
  'mcp_app',
  'dedicated_agents_off',
  'server_overrides_account',
  'choice_suspended',
] as const;
export type MCPBehaviorNote = (typeof MCP_BEHAVIOR_NOTES)[number];

export const MCP_DRIVER_KINDS = ['direct', 'dedicated_agent'] as const;
export type MCPDriverKind = (typeof MCP_DRIVER_KINDS)[number];

export const MCP_CONFIRMATION_SOURCES = ['server', 'account', 'instance'] as const;
export type MCPConfirmationSource = (typeof MCP_CONFIRMATION_SOURCES)[number];

export const MCP_EXECUTION_MODES = ['pipeline', 'react'] as const;
export type MCPExecutionMode = (typeof MCP_EXECUTION_MODES)[number];

export interface MCPModeBehavior {
  driver: MCPDriverKind;
  before_task: boolean;
  per_call: MCPQuestionFlow | null;
}

export interface MCPToolBehavior {
  tool_name: string;
  title: string | null;
  /** What the server says the tool does — a third party's text. */
  description: string | null;
  /** LIA asks before this call in both modes — before the task, for a dedicated agent. */
  asks: boolean;
  reason: MCPConfirmationReason;
  /** The tool's own choice that applies; null when the levels below decide. */
  choice: MCPToolChoice | null;
  /** A « never » made against another declaration: it does not apply. */
  suspended: boolean;
  /** Whether LIA would ask without a choice of its own — what « by default » gives. */
  default_asks: boolean;
}

export interface MCPServerBehavior {
  confirmation: { always: boolean; source: MCPConfirmationSource };
  pipeline: MCPModeBehavior;
  react: MCPModeBehavior;
  tools: MCPToolBehavior[];
  unattended_refused: string[];
  notes: MCPBehaviorNote[];
}

/** A tool LIA asks about now and would no longer ask about after a change. */
export interface MCPQuestionLoss {
  server_id: string;
  server_name: string;
  tool_name: string;
}

export interface MCPBehaviorPreview {
  behavior: MCPServerBehavior;
  questions_lost: MCPQuestionLoss[];
}

export interface MCPStrategyPreview {
  questions_lost: MCPQuestionLoss[];
}

/** Whether the synthesis says the server is an MCP App; unknown until it is read. */
export function isMcpApp(behavior: MCPServerBehavior | undefined): boolean {
  return behavior?.notes.includes('mcp_app') ?? false;
}

/** The candidate values the server form sends to the preview; absent = as stored. */
export interface MCPBehaviorCandidates {
  hitl_required?: boolean | null;
  iterative_mode?: boolean;
  react_expand_iterative?: boolean | null;
  /** By tool name; null returns a tool to the levels below. */
  tool_choices?: Record<string, MCPToolChoice | null>;
}

/** One tool's choice, as written (an explicit null returns it to the levels below). */
export interface MCPToolConfirmationRequest {
  tool_name: string;
  choice: MCPToolChoice | null;
}

/** A confirmation as the page offers it: the server's or the account's choice. */
export const MCP_CONFIRMATION_CHOICES = ['always', 'as_declared', 'inherit'] as const;
export type MCPConfirmationChoice = (typeof MCP_CONFIRMATION_CHOICES)[number];

export function confirmationChoiceOf(value: boolean | null | undefined): MCPConfirmationChoice {
  if (value === true) return 'always';
  if (value === false) return 'as_declared';
  return 'inherit';
}

export function confirmationValueOf(choice: MCPConfirmationChoice): boolean | null {
  if (choice === 'always') return true;
  if (choice === 'as_declared') return false;
  return null;
}

/** Who drives a server, as ONE choice (spec 2026-10-30 D4). */
export const MCP_DRIVERS = ['direct', 'pipeline_agent', 'agent_everywhere'] as const;
export type MCPDriver = (typeof MCP_DRIVERS)[number];

export function driverOf(
  iterative: boolean,
  shape: boolean | null,
  defaults: Pick<UserMCPDefaults, 'react_direct_tools_default' | 'dedicated_agents_available'>
): MCPDriver {
  if (!iterative || !defaults.dedicated_agents_available) return 'direct';
  return (shape ?? defaults.react_direct_tools_default) ? 'pipeline_agent' : 'agent_everywhere';
}

export function driverValues(driver: MCPDriver): {
  iterative_mode: boolean;
  react_expand_iterative?: boolean;
} {
  if (driver === 'direct') return { iterative_mode: false };
  return { iterative_mode: true, react_expand_iterative: driver === 'pipeline_agent' };
}

export type MCPDriverAvailability = 'available' | 'dedicated_agents_off' | 'mcp_app';

/** Whether the page may offer a driver here — never a shape the ReAct selector will not take. */
export function driverAvailability(
  driver: MCPDriver,
  defaults: Pick<UserMCPDefaults, 'dedicated_agents_available'>,
  isMcpApp: boolean
): MCPDriverAvailability {
  if (driver === 'direct') return 'available';
  if (!defaults.dedicated_agents_available) return 'dedicated_agents_off';
  if (driver === 'pipeline_agent' && isMcpApp) return 'mcp_app';
  return 'available';
}
