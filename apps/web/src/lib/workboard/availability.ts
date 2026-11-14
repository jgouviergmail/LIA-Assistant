/**
 * Whether the workboard is offered now: the verdict of its header destination.
 *
 * The operator's switch decides when the configuration carries the capability
 * map, the deployment ceiling otherwise (`capabilityEnabled`); an unknown
 * configuration offers nothing, so the destination never flashes in before
 * `/config` answers.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

interface WorkboardConfig {
  features?: { workboard_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration (`useAppConfig().config`), possibly not loaded.
 * @returns Whether the workboard is offered.
 */
export function workboardAvailable(config: WorkboardConfig | null | undefined): boolean {
  return capabilityEnabled(config?.capabilities, 'workboard', config?.features?.workboard_enabled);
}
