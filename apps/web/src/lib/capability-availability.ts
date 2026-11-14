/**
 * Whether a capability is offered NOW, and whether its record is readable —
 * the door of every capability that has no module of its own (ADR-280).
 *
 * `/config` publishes two facts about a capability: the deployment flag that
 * MOUNTS its routes (`features.<x>_enabled`) and, in `capabilities`, its
 * effective state — the flag AND the operator's switch. A screen that offers
 * an ACT asks `capabilityAvailable`: the switch can close the routes the flag
 * mounted, and what it closed must not be offered. A screen that shows a
 * RECORD asks `capabilityMounted`: a switch removes the capability, never what
 * it produced (decision 2).
 *
 * Three capabilities have no published flag — the psyche, the personal MCP
 * servers and image generation. The map alone answers for them, and nothing
 * can ask for their record here: `capabilityMounted` needs a flag.
 *
 * One router is mounted by a flag that is NOT its capability's ceiling: the
 * personal MCP servers. The map says « offered » from the ceiling and the
 * switch, and cannot say that router is absent — `CAPABILITY_ROUTER_FLAGS`
 * names the flag `/config` publishes for it, and the door closes on it.
 *
 * Nothing else reads these flags (`capability-flags.guard.test.ts`). Nine
 * screens read the ceiling for an act, one after the other, and each opened on
 * a refusal once the operator had switched its capability off.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

/**
 * Capability key (`capabilities.<key>`) → the deployment flag that mounts it,
 * or null where `/config` publishes none.
 */
export const CAPABILITY_CEILING = {
  attachments: 'attachments_enabled',
  avatar: 'avatar_enabled',
  channels: 'channels_enabled',
  habits: 'habits_enabled',
  heartbeat: 'heartbeat_enabled',
  image_generation: null,
  journals: 'journals_enabled',
  live: 'live_enabled',
  mcp: null,
  open_loops: 'open_loops_enabled',
  psyche: null,
  python_sandbox_egress: 'python_sandbox_egress_enabled',
  // ADR-386: a server that publishes no ceiling predates the third clock.
  routine_webhooks: 'routine_webhooks_enabled',
  skills: 'skills_enabled',
  telephony: 'telephony_enabled',
} as const satisfies Record<string, keyof AppConfig['features'] | null>;

/**
 * Capability key → the flags that mount its ROUTER without being its ceiling.
 *
 * The API finds them on its own routes (`capability_route_table.json`,
 * `router_flags`); `capability-flags.guard.test.ts` holds this table equal.
 */
export const CAPABILITY_ROUTER_FLAGS = {
  mcp: ['mcp_user_enabled'],
} as const satisfies Partial<
  Record<keyof typeof CAPABILITY_CEILING, readonly (keyof AppConfig['features'])[]>
>;

/** A capability this door answers for. */
export type DoorCapability = keyof typeof CAPABILITY_CEILING;

/** A capability whose deployment flag is published: its record can be asked for. */
export type FlaggedCapability = {
  [Capability in DoorCapability]: (typeof CAPABILITY_CEILING)[Capability] extends null
    ? never
    : Capability;
}[DoorCapability];

/** The part of the app configuration the door reads. */
export interface CapabilityConfig {
  features?: Partial<AppConfig['features']>;
  capabilities?: AppConfig['capabilities'];
}

function isFlagged(capability: DoorCapability): capability is FlaggedCapability {
  return CAPABILITY_CEILING[capability] !== null;
}

/**
 * Whether the deployment says it mounts no router for the capability.
 *
 * Only an explicit « off » closes: a server that publishes none of these
 * flags predates them, and what it offered is still there.
 */
function routerUnmounted(
  config: CapabilityConfig | null | undefined,
  capability: DoorCapability
): boolean {
  const flags: Partial<Record<DoorCapability, readonly (keyof AppConfig['features'])[]>> =
    CAPABILITY_ROUTER_FLAGS;
  return (flags[capability] ?? []).some(flag => config?.features?.[flag] === false);
}

/**
 * The deployment flag alone — for a RECORD, readable whatever the switch says.
 *
 * @param config - The app configuration, possibly not loaded.
 * @param capability - The capability whose routes the flag mounts.
 * @param unpublished - The answer where no flag is published (an older API,
 *   or a configuration not loaded yet): off, unless the capability predates
 *   its flag.
 * @returns Whether the deployment mounts the capability.
 */
export function capabilityMounted(
  config: CapabilityConfig | null | undefined,
  capability: FlaggedCapability,
  unpublished = false
): boolean {
  const flag = config?.features?.[CAPABILITY_CEILING[capability]];
  return typeof flag === 'boolean' ? flag : unpublished;
}

/**
 * Whether the instance offers the capability now — for an ACT.
 *
 * @param config - The app configuration, possibly not loaded.
 * @param capability - The capability the act belongs to.
 * @param unpublished - The deployment's answer where it publishes no flag for
 *   a capability that has one; unused for those that have none.
 * @returns False where the deployment mounts no router for it. Else the
 *   operator's verdict when the map carries the capability; else the
 *   deployment flag — and, for a capability with no published flag, true once
 *   a configuration is there: a server that sends none of the map predates
 *   the switches, and the capability was always offered.
 */
export function capabilityAvailable(
  config: CapabilityConfig | null | undefined,
  capability: DoorCapability,
  unpublished = false
): boolean {
  if (routerUnmounted(config, capability)) return false;
  const ceiling = isFlagged(capability)
    ? capabilityMounted(config, capability, unpublished)
    : Boolean(config);
  return capabilityEnabled(config?.capabilities, capability, ceiling);
}
