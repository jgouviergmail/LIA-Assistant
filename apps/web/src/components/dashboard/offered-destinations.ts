/**
 * The destinations this instance offers NOW — one list for the header, the
 * menu the logo opens on a phone and the world's « Application » links.
 *
 * `visibleDestinations` reads flags; WHICH value each flag takes is decided
 * here, once. The deployment ceiling mounts a section's routes and the
 * operator's switch can still close them (ADR-280): every gated destination
 * is offered where the instance offers it now, so a destination the operator
 * switched off is a dead link nowhere. The header spelled four of the six by
 * hand and read the meetings and the knowledge spaces from their ceilings;
 * the world's list read the ceilings alone.
 */
import { worldAvailable } from '@/features/world/availability';
import type { AppConfig } from '@/hooks/useAppConfig';
import {
  visibleDestinations,
  type DashboardDestination,
  type DestinationFeatures,
} from '@/lib/dashboard-nav';
import { meetingsAvailable } from '@/lib/meetings/availability';
import { ragSpacesAvailable } from '@/lib/rag-spaces/availability';
import { smsAvailable } from '@/lib/sms/availability';
import { workbenchAvailable } from '@/lib/workbench/availability';
import { workboardAvailable } from '@/lib/workboard/availability';

/** What the list is read from: the deployment's ceilings and the operator's switches. */
export interface OfferConfig {
  features?: DestinationFeatures;
  capabilities?: AppConfig['capabilities'];
}

/**
 * @param config - The app configuration (`useAppConfig().config`), possibly not loaded.
 * @returns The destinations of the table this instance offers now, in order.
 */
export function offeredDestinations(
  config: OfferConfig | null | undefined
): readonly DashboardDestination[] {
  // `Required`: a flag added to the table with no door here fails the type
  // check, rather than hiding its destination or reading a ceiling.
  const offered: Required<DestinationFeatures> = {
    world_enabled: worldAvailable(config),
    workbench_enabled: workbenchAvailable(config),
    sms_enabled: smsAvailable(config),
    meetings_enabled: meetingsAvailable(config),
    workboard_enabled: workboardAvailable(config),
    rag_spaces_enabled: ragSpacesAvailable(config),
  };
  return visibleDestinations(offered);
}
