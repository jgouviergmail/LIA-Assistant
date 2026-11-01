/**
 * Whether the « Tools » section is offered now (ADR-369): one verdict for the
 * header destination, the logo menu and the pages under it.
 *
 * The operator's switch decides when the configuration carries the capability
 * map, the deployment ceiling otherwise (`capabilityEnabled`); an unknown
 * configuration offers nothing, so the destination never flashes in before
 * `/config` answers.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

interface WorkbenchConfig {
  features?: { workbench_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration (`useAppConfig().config`), possibly not loaded.
 * @returns Whether the section is offered.
 */
export function workbenchAvailable(config: WorkbenchConfig | null | undefined): boolean {
  return capabilityEnabled(config?.capabilities, 'workbench', config?.features?.workbench_enabled);
}
