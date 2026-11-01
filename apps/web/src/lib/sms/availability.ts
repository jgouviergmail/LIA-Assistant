/**
 * Whether SMS are offered now: one verdict for the header destination, the
 * « SMS » page, the settings section and the alerts hub.
 *
 * The operator's switch decides when the configuration carries the capability
 * map, the deployment ceiling otherwise (`capabilityEnabled`); an unknown
 * configuration offers nothing, so the destination never flashes in before
 * `/config` answers.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

interface SmsConfig {
  features?: { sms_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration (`useAppConfig().config`), possibly not loaded.
 * @returns Whether SMS are offered.
 */
export function smsAvailable(config: SmsConfig | null | undefined): boolean {
  return capabilityEnabled(config?.capabilities, 'sms', config?.features?.sms_enabled);
}
