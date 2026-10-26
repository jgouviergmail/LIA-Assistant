/** One effective operator/deployment verdict for the menu and the world entry. */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

interface WorldConfig {
  features?: { world_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

export function worldAvailable(config: WorldConfig | null | undefined): boolean {
  return capabilityEnabled(config?.capabilities, 'world', config?.features?.world_enabled);
}
