/** The category selector offers exactly the sections this hub serves. */
import type { AppConfig } from '@/hooks/useAppConfig';
import type { AlertCategory } from './alert-query';
import { capabilityMounted } from './capability-availability';
import { capabilityEnabled } from './capability-state';
import { peersAvailable } from './peers/image-share';
import { smsAvailable } from './sms/availability';
import { workboardAvailable } from './workboard/availability';

export function alertCategoryAvailability(
  config: AppConfig | null | undefined
): Record<AlertCategory, boolean> {
  return {
    // The messages are read from the connections' own router, which refuses
    // once the operator switched them off.
    peer_messages: peersAvailable(config ?? null),
    // What was sent is a RECORD: its history stays readable under the
    // deployment flag, whatever the switch says.
    proactive: capabilityMounted(config, 'heartbeat'),
    interests: true,
    reminders: true,
    scheduled: true,
    workboard: workboardAvailable(config),
    discussions: capabilityEnabled(config?.capabilities, 'proactive_discussions', false),
    sms: smsAvailable(config),
  };
}
