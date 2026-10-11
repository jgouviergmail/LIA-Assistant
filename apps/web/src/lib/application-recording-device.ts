/** Finite commands dispatch only through the current account's original recorder. */
import { z } from '@/lib/zod';
import type { MeetingRecorderPhase } from '@/stores/meetingRecorderStore';

const phase = z.enum([
  'idle',
  'starting',
  'recording',
  'offline',
  'stopping',
  'processing',
  'interrupted',
  'error',
]);
const action = z.enum(['start', 'stop', 'resume', 'finalize_with_gaps', 'discard']);
export const recordingDeviceSnapshotSchema = z
  .object({
    actor_id: z.string().uuid(),
    observed_at: z.string().datetime({ offset: true }),
    supported: z.boolean(),
    phase,
    meeting_id: z.string().uuid().nullable(),
  })
  .strict()
  .refine(state =>
    ['idle', 'starting'].includes(state.phase)
      ? state.meeting_id === null
      : state.phase === 'error' || state.meeting_id !== null
  );
export const recordingDeviceClaimSchema = z
  .object({
    command_id: z.string().uuid(),
    claim_token: z.string().uuid(),
    expires_at: z.string().datetime({ offset: true }),
    intent: z.object({ action, phase, meeting_id: z.string().uuid().nullable() }).strict(),
  })
  .strict();
export type RecordingDeviceClaim = z.infer<typeof recordingDeviceClaimSchema>;
export type RecordingDeviceAction = RecordingDeviceClaim['intent']['action'];
export type RecordingDeviceState = {
  phase: MeetingRecorderPhase;
  meeting_id: string | null;
  supported: boolean;
};
export type RecordingDeviceAck = {
  claim_token: string;
  result: 'completed' | 'refused' | 'unknown';
  phase: MeetingRecorderPhase;
  meeting_id: string | null;
};
export type RecordingDeviceOwner = {
  snapshot: () => RecordingDeviceState;
  execute: (action: RecordingDeviceAction) => Promise<void>;
};

type Registration = { actorId: string; owner: RecordingDeviceOwner; spent: Map<string, number> };
let registered: Registration | undefined;

export function registerRecordingDevice(actorId: string, owner: RecordingDeviceOwner): () => void {
  const registration = { actorId, owner, spent: new Map<string, number>() };
  registered = registration;
  return () => {
    if (registered === registration) registered = undefined;
  };
}

export function recordingDeviceSnapshot(actorId: string) {
  if (registered?.actorId !== actorId) return undefined;
  const parsed = recordingDeviceSnapshotSchema.safeParse({
    actor_id: actorId,
    observed_at: new Date().toISOString(),
    ...registered.owner.snapshot(),
  });
  return parsed.success ? parsed.data : undefined;
}

function completed(
  action: RecordingDeviceAction,
  original: string | null,
  state: RecordingDeviceState
): boolean {
  if (action === 'discard') return state.phase === 'idle' && state.meeting_id === null;
  if (action === 'start')
    return ['recording', 'offline'].includes(state.phase) && state.meeting_id !== null;
  return (
    state.meeting_id === original &&
    (action === 'resume' ? ['recording', 'offline'] : ['processing']).includes(state.phase)
  );
}

export async function executeRecordingDeviceCommand(
  actorId: string,
  command: RecordingDeviceClaim
): Promise<RecordingDeviceAck> {
  const registration = registered;
  const fallback: RecordingDeviceAck = {
    claim_token: command.claim_token,
    result: 'refused',
    phase: command.intent.phase,
    meeting_id: command.intent.meeting_id,
  };
  if (!registration || registration.actorId !== actorId) return fallback;
  const now = Date.now();
  for (const [id, expiry] of registration.spent) if (expiry <= now) registration.spent.delete(id);
  const expiry = Date.parse(command.expires_at);
  const before = registration.owner.snapshot();
  if (
    !Number.isFinite(expiry) ||
    expiry <= now ||
    registration.spent.has(command.command_id) ||
    !before.supported ||
    before.phase !== command.intent.phase ||
    before.meeting_id !== command.intent.meeting_id
  )
    return fallback;
  // Consume before invoking an owner that may change state and then throw.
  registration.spent.set(command.command_id, expiry);
  try {
    await registration.owner.execute(command.intent.action);
    if (registered !== registration) return { ...fallback, result: 'unknown' };
    const state = registration.owner.snapshot();
    return {
      claim_token: command.claim_token,
      result: completed(command.intent.action, before.meeting_id, state) ? 'completed' : 'refused',
      phase: state.phase,
      meeting_id: state.meeting_id,
    };
  } catch {
    return { ...fallback, result: 'unknown' };
  }
}
