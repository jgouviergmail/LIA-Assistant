/** The category selector offers exactly the sections this hub serves. */
import type { AppConfig } from '@/hooks/useAppConfig';
import type { AlertCategory } from './alert-query';
import { capabilityEnabled } from './capability-state';
import { smsAvailable } from './sms/availability';

export function alertCategoryAvailability(
  config: AppConfig | null | undefined
): Record<AlertCategory, boolean> {
  const features = config?.features;
  return {
    peer_messages: Boolean(features?.peers_enabled),
    proactive: Boolean(features?.heartbeat_enabled),
    interests: true,
    reminders: true,
    scheduled: true,
    workboard: Boolean(features?.workboard_enabled),
    discussions: capabilityEnabled(config?.capabilities, 'proactive_discussions', false),
    sms: smsAvailable(config),
  };
}
