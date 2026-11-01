import type { MCPServerBehavior, MCPToolBehavior, UserMCPDefaults } from '@/lib/mcp-behavior';

/** What a choice left open inherits — the instance follows its declarations. */
export function mcpDefaultsFixture(overrides: Partial<UserMCPDefaults> = {}): UserMCPDefaults {
  return {
    confirmation_instance: false,
    confirmation_account: null,
    confirmation_effective: false,
    react_direct_tools_default: true,
    dedicated_agents_available: true,
    ...overrides,
  };
}

export function mcpToolBehaviorFixture(overrides: Partial<MCPToolBehavior> = {}): MCPToolBehavior {
  return {
    tool_name: 'delete_note',
    title: null,
    description: null,
    asks: true,
    reason: 'declared_destructive',
    choice: null,
    suspended: false,
    default_asks: true,
    ...overrides,
  };
}

/** A server driven directly, following its declarations: one destructive tool. */
export function mcpBehaviorFixture(overrides: Partial<MCPServerBehavior> = {}): MCPServerBehavior {
  return {
    confirmation: { always: false, source: 'instance' },
    pipeline: { driver: 'direct', before_task: false, per_call: 'card_after_task' },
    react: { driver: 'direct', before_task: false, per_call: 'in_loop' },
    tools: [mcpToolBehaviorFixture()],
    unattended_refused: ['delete_note'],
    notes: [],
    ...overrides,
  };
}
