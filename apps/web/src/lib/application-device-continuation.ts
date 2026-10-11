/** Transport claim precedes the local effect; uncertain transport never grants replay. */
import apiClient from '@/lib/api-client';
import {
  executeRecordingDeviceCommand,
  recordingDeviceClaimSchema,
} from '@/lib/application-recording-device';
import type { ApplicationCommandStatus } from '@/types/application-commands';

export function isWaitingRecordingCommand(
  status: ApplicationCommandStatus | null
): status is ApplicationCommandStatus {
  return (
    status?.phase === 'waiting' &&
    status.interaction?.kind === 'device' &&
    status.operation_id === 'meeting_device.control'
  );
}

export async function continueRecordingDeviceCommand(
  actorId: string,
  commandId: string,
  isCurrent: () => boolean
): Promise<unknown | null> {
  const endpoint = `/application-commands/${encodeURIComponent(commandId)}/device`;
  const raw = await apiClient.post<unknown>(`${endpoint}/claim`);
  if (!isCurrent() || raw === null) return null;
  const claim = recordingDeviceClaimSchema.parse(raw);
  if (claim.command_id !== commandId) throw new Error('Invalid command identity');
  const ack = await executeRecordingDeviceCommand(actorId, claim);
  if (!isCurrent()) return null;
  return await apiClient.post<unknown>(`${endpoint}/ack`, ack);
}
