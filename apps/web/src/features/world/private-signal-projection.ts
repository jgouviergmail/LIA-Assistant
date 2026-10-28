/** Owner-local object attention. No notice identity or body enters the painter. */
import { z } from '@/lib/zod';
import type { GeneratedAssetFamily } from '@/types/generated-assets';
import type { DeviceNotice } from './device-inbox';
import type { WorldDefinition, WorldProp } from './types';

export type PrivateSignalKind = 'sms' | 'reminder' | 'workboard' | GeneratedAssetFamily;
export interface ResourceSignal {
  status: 'unknown' | 'unavailable' | 'ready';
  count: number | null;
  firstId: string | null;
}
export const UNKNOWN_RESOURCE: Readonly<ResourceSignal> = {
  status: 'unknown',
  count: null,
  firstId: null,
};
const unavailable: Readonly<ResourceSignal> = { status: 'unavailable', count: null, firstId: null };
const rows = z.array(z.object({ id: z.uuid() })).max(1);
const page = z.object({
  total: z
    .number()
    .int()
    .min(0)
    .max(2 ** 31 - 1),
  items: rows.optional(),
  tickets: rows.optional(),
});
/** Read the native first-page aggregate without carrying titles, filenames or bodies. */
export function readResourceSignal(
  payload: unknown,
  collection: 'tickets' | 'items'
): ResourceSignal {
  const parsed = page.safeParse(payload);
  if (!parsed.success) return unavailable;
  const items = parsed.data[collection];
  if (!items || parsed.data.total > 0 !== (items.length === 1)) return unavailable;
  return { status: 'ready', count: parsed.data.total, firstId: items[0]?.id ?? null };
}
export interface PrivateSignalInputs {
  ownerId: string;
  snapshotOwnerId: string;
  enabled: boolean;
  smsEnabled: boolean;
  workboardEnabled: boolean;
  assetsEnabled: boolean;
  entries: readonly DeviceNotice[];
  workboard: ResourceSignal;
  images: ResourceSignal;
  documents: ResourceSignal;
  screenshots: ResourceSignal;
}
export type PrivateSignalTarget =
  | { kind: 'notice'; noticeKey: string }
  | { kind: 'workboard'; ticketId: string }
  | { kind: 'gallery'; tab: GeneratedAssetFamily };
export interface PrivateObjectSignal {
  propId: string;
  kind: PrivateSignalKind;
  count: number | null;
  status: 'ready' | 'unavailable';
  target: PrivateSignalTarget | null;
}
export type PrivateSignalPresentation = Omit<PrivateObjectSignal, 'target'>;
export function signalPresentation(
  signals: readonly PrivateObjectSignal[]
): readonly PrivateSignalPresentation[] {
  return signals.map(({ propId, kind, count, status }) => ({ propId, kind, count, status }));
}
function supportFamily(prop: WorldProp): PrivateSignalKind | null {
  if (prop.kind === 'smartphone' && prop.activity === 'sms') return 'sms';
  if (prop.kind === 'alarm' && prop.activity === 'reminders') return 'reminder';
  if (prop.kind === 'writingdesk' && prop.activity === 'workboard') return 'workboard';
  if (prop.kind !== 'easel') return null;
  switch (prop.activity) {
    case 'asset-images':
      return 'images';
    case 'asset-documents':
      return 'documents';
    case 'asset-screenshots':
      return 'screenshots';
    default:
      return null;
  }
}
function noticeSignal(
  propId: string,
  kind: 'sms' | 'reminder',
  input: PrivateSignalInputs
): PrivateObjectSignal | null {
  if (kind === 'sms' && !input.smsEnabled) return null;
  const unread = input.entries.filter(notice => notice.kind === kind && !notice.read);
  const notice = unread[0];
  return notice
    ? {
        propId,
        kind,
        status: 'ready',
        count: unread.length,
        target: { kind: 'notice', noticeKey: notice.key },
      }
    : null;
}
function resourceSignal(
  propId: string,
  kind: Exclude<PrivateSignalKind, 'sms' | 'reminder'>,
  input: PrivateSignalInputs
): PrivateObjectSignal | null {
  if (!(kind === 'workboard' ? input.workboardEnabled : input.assetsEnabled)) return null;
  const resource = input[kind];
  if (resource.status === 'unknown' || resource.count === 0) return null;
  const target = resource.status === 'unavailable' ? null : resourceTarget(kind, resource.firstId);
  return { propId, kind, status: resource.status, count: resource.count, target };
}
function resourceTarget(
  kind: Exclude<PrivateSignalKind, 'sms' | 'reminder'>,
  firstId: string | null
): PrivateSignalTarget | null {
  if (kind === 'workboard') return firstId ? { kind: 'workboard', ticketId: firstId } : null;
  return { kind: 'gallery', tab: kind };
}
export function projectPrivateSignals(
  world: WorldDefinition,
  input: PrivateSignalInputs
): readonly PrivateObjectSignal[] {
  if (!input.enabled || input.ownerId !== input.snapshotOwnerId) return [];
  return world.props.flatMap(prop => {
    const kind = supportFamily(prop);
    if (!kind) return [];
    const signal =
      kind === 'sms' || kind === 'reminder'
        ? noticeSignal(prop.id, kind, input)
        : resourceSignal(prop.id, kind, input);
    return signal ? [signal] : [];
  });
}
