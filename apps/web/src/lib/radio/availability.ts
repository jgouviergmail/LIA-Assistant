/**
 * Whether the instance offers the radio now (ADR-324) — the EFFECTIVE state.
 *
 * The capability map carries the operator's switch as well as the deployment
 * ceiling; an API that omits it falls back to the ceiling alone (the shape of
 * `emailShareAvailable`). The header control, the logo menu, the dashboard's
 * card, the page and the settings section all read this one answer, so a
 * switched-off radio is offered nowhere rather than refused everywhere.
 */
import type { AppConfig } from '@/hooks/useAppConfig';

export interface RadioConfig {
  features?: { radio_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration, or null while it loads.
 * @returns True when a session could start.
 */
export function radioAvailable(config: RadioConfig | null | undefined): boolean {
  const capability = config?.capabilities?.radio;
  return capability ? capability.enabled : Boolean(config?.features?.radio_enabled);
}
