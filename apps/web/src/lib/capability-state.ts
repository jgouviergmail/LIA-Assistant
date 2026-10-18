/**
 * The EFFECTIVE state of one platform capability, as the web reads it (ADR-280).
 *
 * The capability map of `/config` carries the operator's switch as well as the
 * deployment ceiling; an API that omits the map (an older server) falls back to
 * the ceiling alone. Every « is this offered now? » question of the web asks
 * this one rule — four features used to spell it each on their own — so a
 * switched-off capability is offered nowhere rather than refused everywhere.
 */
import type { AppConfig } from '@/hooks/useAppConfig';

/**
 * @param capabilities - The capability map of the app configuration, if any.
 * @param key - The capability's key in that map (`capabilities.items.<key>`).
 * @param ceiling - The deployment flag that mounts the capability's routes.
 * @returns The operator's verdict when the map carries the capability, else the ceiling.
 */
export function capabilityEnabled(
  capabilities: AppConfig['capabilities'] | undefined,
  key: string,
  ceiling: boolean | undefined
): boolean {
  const capability = capabilities?.[key];
  return capability ? capability.enabled : Boolean(ceiling);
}
