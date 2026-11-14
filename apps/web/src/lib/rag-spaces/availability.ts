/**
 * Whether the knowledge spaces are offered now.
 *
 * The operator's switch decides when the configuration carries the capability
 * map, the deployment ceiling otherwise (`capabilityEnabled`); an unknown
 * configuration offers nothing, so nothing flashes in before `/config`
 * answers.
 */
import type { AppConfig } from '@/hooks/useAppConfig';
import { capabilityEnabled } from '@/lib/capability-state';

interface RagSpacesConfig {
  features?: { rag_spaces_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration (`useAppConfig().config`), possibly not loaded.
 * @returns Whether the knowledge spaces are offered.
 */
export function ragSpacesAvailable(config: RagSpacesConfig | null | undefined): boolean {
  return capabilityEnabled(
    config?.capabilities,
    'rag_spaces',
    config?.features?.rag_spaces_enabled
  );
}
