import type {
  CardActionItem,
  CardActionsProjection,
  CardComposeAction,
  CardCompositionWire,
} from '@/types/card-actions';
import type { Message, BrowserContext } from '@/types/chat';

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function action(value: unknown): value is CardComposeAction {
  return (
    value === 'reply' ||
    value === 'forward' ||
    value === 'delete_email' ||
    value === 'cancel_reminder'
  );
}
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;

/** Python's schema bounds Unicode code points, not JavaScript's UTF-16 units. */
export function isCardActionLabel(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 400 && [...value].length <= 200;
}

export function cardCompositionWire(value: unknown): CardCompositionWire | null {
  if (
    !record(value) ||
    !exactKeys(value, ['version', 'message_id', 'run_id', 'registry_id', 'action'])
  )
    return null;
  if (value.version !== 1 || typeof value.message_id !== 'string' || !UUID.test(value.message_id))
    return null;
  if (typeof value.run_id !== 'string' || !value.run_id || value.run_id.length > 256) return null;
  if (
    typeof value.registry_id !== 'string' ||
    !/^[A-Za-z0-9_-]{1,128}$/.test(value.registry_id) ||
    !action(value.action)
  )
    return null;
  return {
    version: 1,
    message_id: value.message_id,
    run_id: value.run_id,
    registry_id: value.registry_id,
    action: value.action,
  };
}

function identity(
  value: unknown
): { registry_id: string; target_id: string; label: string } | null {
  if (
    !record(value) ||
    !exactKeys(value, [
      'registry_id',
      'kind',
      'target_id',
      'provider',
      'account_binding',
      'label',
      'actions',
    ])
  )
    return null;
  if (typeof value.registry_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(value.registry_id))
    return null;
  if (typeof value.target_id !== 'string' || !/^[A-Za-z0-9._~+=/-]{1,2048}$/.test(value.target_id))
    return null;
  if (!isCardActionLabel(value.label)) return null;
  return { registry_id: value.registry_id, target_id: value.target_id, label: value.label };
}
function emailItem(
  common: Pick<CardActionItem, 'registry_id' | 'target_id' | 'label'>,
  value: Record<string, unknown>
): CardActionItem | null {
  if (
    !Array.isArray(value.actions) ||
    (value.actions.length !== 2 && value.actions.length !== 3) ||
    value.actions[0] !== 'reply' ||
    value.actions[1] !== 'forward' ||
    (value.actions.length === 3 && value.actions[2] !== 'delete_email')
  )
    return null;
  const provider = value.provider;
  if (provider !== 'google_gmail' && provider !== 'microsoft_outlook') return null;
  if (typeof value.account_binding !== 'string' || !UUID.test(value.account_binding)) return null;
  return {
    ...common,
    kind: 'EMAIL',
    provider,
    account_binding: value.account_binding,
    actions:
      value.actions.length === 3 ? ['reply', 'forward', 'delete_email'] : ['reply', 'forward'],
  };
}

function item(value: unknown): CardActionItem | null {
  const common = identity(value);
  if (!common || !record(value) || !Array.isArray(value.actions)) return null;
  if (value.kind === 'EMAIL') return emailItem(common, value);
  if (
    value.kind === 'REMINDER' &&
    UUID.test(common.target_id) &&
    value.provider === null &&
    value.account_binding === null &&
    value.actions.length === 1 &&
    value.actions[0] === 'cancel_reminder'
  )
    return {
      ...common,
      kind: 'REMINDER',
      provider: null,
      account_binding: null,
      actions: ['cancel_reminder'],
    };
  return null;
}

export function cardSourceMessageId(message: Message): string | undefined {
  const value = message.metadata?.message_db_id;
  return typeof value === 'string' && UUID.test(value) ? value : undefined;
}

export function withCardCompositionContext(
  context: BrowserContext,
  selection?: CardCompositionWire
): BrowserContext {
  return selection ? { ...context, card_composition: selection } : context;
}

export function withCompositionUserMetadata(
  message: Message,
  selection?: CardCompositionWire
): Message {
  return selection
    ? { ...message, metadata: { ...message.metadata, card_composition: selection } }
    : message;
}

export function retryCardComposition(message: Message): CardCompositionWire | undefined {
  return cardCompositionWire(message.metadata?.retryCardComposition) ?? undefined;
}

export function retryFromCardMessage(
  onRetry: (text: string, selection?: CardCompositionWire) => void,
  text: string,
  message: Message
): void {
  const selection = retryCardComposition(message);
  if (selection) onRetry(text, selection);
  else onRetry(text);
}

export function retryCompositionMetadata(userMessage?: Message): Record<string, unknown> {
  const selection = cardCompositionWire(userMessage?.metadata?.card_composition);
  return selection ? { retryCardComposition: selection } : {};
}

export function cardActionsFromMetadata(metadata: unknown): CardActionsProjection | null {
  if (!record(metadata) || !record(metadata.lia_card_actions)) return null;
  const projection = metadata.lia_card_actions;
  if (!exactKeys(projection, ['version', 'run_id', 'items'])) return null;
  if (
    projection.version !== 1 ||
    typeof projection.run_id !== 'string' ||
    !projection.run_id ||
    projection.run_id.length > 256 ||
    projection.run_id !== metadata.run_id
  )
    return null;
  if (!Array.isArray(projection.items) || !projection.items.length || projection.items.length > 256)
    return null;
  const targets = projection.items.map(item);
  if (targets.some(target => target === null)) return null;
  const valid = targets.filter((target): target is CardActionItem => target !== null);
  if (new Set(valid.map(target => target.registry_id)).size !== valid.length) return null;
  return { version: 1, run_id: projection.run_id, items: valid };
}

export function cardActionDoneMetadata(
  metadata: unknown,
  previous: unknown
): Record<string, unknown> {
  if (record(metadata) && metadata.cancelled) return {};
  const projection = cardActionsFromMetadata(metadata);
  if (
    !projection ||
    (record(previous) &&
      typeof previous.run_id === 'string' &&
      previous.run_id !== projection.run_id)
  )
    return {};
  return { run_id: projection.run_id, lia_card_actions: projection };
}
export function withCardActionDoneMetadata(message: Message, metadata: unknown): Message {
  return {
    ...message,
    metadata: { ...message.metadata, ...cardActionDoneMetadata(metadata, message.metadata) },
  };
}
