/**
 * Whether the meetings are offered now.
 *
 * The operator's switch decides when the configuration carries the capability
 * map, the deployment ceiling otherwise (`capabilityEnabled`); an unknown
 * configuration offers nothing, so nothing flashes in before `/config`
 * answers.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

interface MeetingsConfig {
  features?: { meetings_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration (`useAppConfig().config`), possibly not loaded.
 * @returns Whether the meetings are offered.
 */
export function meetingsAvailable(config: MeetingsConfig | null | undefined): boolean {
  return capabilityEnabled(config?.capabilities, 'meetings', config?.features?.meetings_enabled);
}
