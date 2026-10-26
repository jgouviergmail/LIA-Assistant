import { PUBLIC_THREAD, preparePublicMessage } from './public-message-protocol';
/** One owned private HTTP lifetime. Recovery reads status; it never retries a send. */
import { ApiError } from '@/lib/api-client';
import {
  messageAck,
  prepareMessage,
  prepareTranslation,
  readMailbox,
  type MailboxScope,
  type MessageWrite,
  type ServerClock,
  type WorldMailbox,
  type TranslationWrite,
} from './message-protocol';

export type SendOutcome = 'accepted' | 'unavailable' | 'uncertain' | 'rejected';
export interface MailboxClientState {
  mailbox: WorldMailbox | null;
  status: 'connecting' | 'online' | 'unavailable';
  sending: 'idle' | 'sending' | 'uncertain' | 'rejected';
  unread: number;
  unreadByRecipient: Readonly<Record<string, number>>;
  operation: 'send' | 'translate' | null;
}
type Endpoint =
  | '/world/messages/read'
  | '/world/messages/send'
  | '/world/messages/public'
  | '/world/messages/status'
  | '/world/messages/translate';
export type MailboxPayload =
  | MailboxScope
  | Readonly<MessageWrite>
  | Readonly<TranslationWrite>
  | (MailboxScope & { id: string });
interface Options {
  getScope(): MailboxScope | null;
  request(endpoint: Endpoint, body: MailboxPayload, signal: AbortSignal): Promise<unknown>;
  onState(state: MailboxClientState): void;
  onAccepted?(intent: Readonly<MessageWrite>): void;
  onRevoked?(): void;
}
const emptyState = (): MailboxClientState => ({
  mailbox: null,
  status: 'connecting',
  sending: 'idle',
  unread: 0,
  unreadByRecipient: {},
  operation: null,
});
type Intent =
  | { kind: 'send'; body: Readonly<MessageWrite> }
  | { kind: 'translate'; body: Readonly<TranslationWrite> };
function appears(intent: Intent, mailbox: WorldMailbox): boolean {
  if (intent.kind === 'translate') {
    const id = intent.body.message_id;
    return mailbox.messages.some(
      message => !message.outgoing && message.id === id && message.text !== null
    );
  }
  if ('recipient' in intent.body)
    return mailbox.messages.some(message => message.outgoing && message.id === intent.body.id);
  return (mailbox.public_messages ?? []).some(
    message => message.outgoing && message.id === intent.body.id
  );
}
function writeEndpoint(intent: Intent): Endpoint {
  if (intent.kind === 'translate') return '/world/messages/translate';
  return 'recipient' in intent.body ? '/world/messages/send' : '/world/messages/public';
}
function sameScope(a: MailboxScope | null, b: MailboxScope): boolean {
  return a?.epoch === b.epoch && a.controller === b.controller;
}
function definitive(error: unknown): boolean {
  return error instanceof ApiError && [400, 401, 403, 409, 422, 429].includes(error.status);
}

export class WorldMailboxClient {
  private running = false;
  private generation = 0;
  private failures = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readAbort: AbortController | null = null;
  private writeAbort: AbortController | null = null;
  private clock: ServerClock | null = null;
  private intent: Intent | null = null;
  private snapshot = emptyState();
  private viewing = false;
  private reader: string | null = null;
  private seen = new Set<string>();
  private refreshRequested = false;

  constructor(private options: Options) {}
  get state(): Readonly<MailboxClientState> {
    return this.snapshot;
  }
  start(): void {
    if (this.running) return;
    this.running = true;
    this.failures = 0;
    document.addEventListener('visibilitychange', this.visibility);
    this.emit({ status: 'connecting' });
    this.refresh();
  }
  private owned(generation: number, scope: MailboxScope): boolean {
    return (
      this.running && generation === this.generation && sameScope(this.options.getScope(), scope)
    );
  }
  /** A write settles for its original owner even during a socket reconnect gap. */
  private ownsIntent(generation: number, intent: Intent): boolean {
    return this.running && generation === this.generation && this.intent === intent;
  }
  private emit(patch: Partial<MailboxClientState>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    if (this.running) this.options.onState(this.snapshot);
  }
  private schedule(delay: number): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.read();
    }, delay);
  }
  private refresh(): void {
    if (!this.running || document.hidden || this.failures >= 5) return;
    if (this.readAbort) {
      this.refreshRequested = true;
      return;
    }
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    void this.read();
  }
  retry(): void {
    this.failures = 0;
    this.emit({ status: 'connecting' });
    this.refresh();
  }
  private visibility = () => {
    if (!document.hidden) {
      this.refresh();
      return;
    }
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.clock = null;
    this.readAbort?.abort();
  };
  private async read(): Promise<void> {
    if (!this.running || this.readAbort || document.hidden) return;
    const scope = this.options.getScope();
    if (!scope) {
      this.clock = null;
      this.schedule(3000);
      return;
    }
    const generation = this.generation;
    const abort = new AbortController();
    this.readAbort = abort;
    try {
      const value = await this.options.request('/world/messages/read', scope, abort.signal);
      if (!this.owned(generation, scope) || abort.signal.aborted) return;
      this.acceptMailbox(readMailbox(value));
    } catch (error) {
      if (this.owned(generation, scope) && !abort.signal.aborted) this.readFailed(error);
    } finally {
      if (this.readAbort === abort) this.readAbort = null;
      this.planRead(generation);
    }
  }
  private planRead(generation: number): void {
    if (!this.running || generation !== this.generation || document.hidden || this.failures >= 5)
      return;
    const delay = this.refreshRequested ? 0 : Math.min(30000, 3000 * 2 ** this.failures);
    this.refreshRequested = false;
    this.schedule(delay);
  }
  private readFailed(error: unknown): void {
    this.clock = null;
    this.failures++;
    const revoked = error instanceof ApiError && [401, 403].includes(error.status);
    if (revoked) this.failures = 5;
    this.emit({
      status: 'unavailable',
      ...(revoked ? { mailbox: null, unread: 0, unreadByRecipient: {} } : {}),
    });
    if (revoked) this.options.onRevoked?.();
  }
  private acceptMailbox(mailbox: WorldMailbox): void {
    this.clock = { serverSeconds: mailbox.server_time, receivedAt: performance.now() };
    this.failures = 0;
    const retained = new Set(
      [...mailbox.messages, ...(mailbox.public_messages ?? [])].map(message => message.id)
    );
    this.seen = new Set([...this.seen].filter(id => retained.has(id)));
    if (this.viewing) this.rememberVisible(mailbox);
    this.emit({ mailbox, status: 'online', ...this.unreadState(mailbox) });
    if (this.intent && this.snapshot.sending === 'uncertain' && appears(this.intent, mailbox))
      this.acceptIntent(this.intent);
  }
  private rememberVisible(mailbox: WorldMailbox): void {
    if (!this.reader) return;
    for (const message of mailbox.messages) {
      if ((message.outgoing ? message.recipient_id : message.sender_id) === this.reader)
        this.seen.add(message.id);
    }
    if (this.reader === PUBLIC_THREAD)
      for (const message of mailbox.public_messages ?? []) this.seen.add(message.id);
  }
  private unreadState(mailbox: WorldMailbox) {
    const unreadByRecipient: Record<string, number> = {};
    let unread = 0;
    for (const message of mailbox.messages) {
      if (message.outgoing || this.seen.has(message.id)) continue;
      unreadByRecipient[message.sender_id] = (unreadByRecipient[message.sender_id] ?? 0) + 1;
      unread++;
    }
    for (const message of mailbox.public_messages ?? []) {
      if (message.outgoing || this.seen.has(message.id)) continue;
      unreadByRecipient[PUBLIC_THREAD] = (unreadByRecipient[PUBLIC_THREAD] ?? 0) + 1;
      unread++;
    }
    return { unread, unreadByRecipient };
  }
  setReading(reading: boolean, recipient: string | null = null): void {
    this.viewing = reading;
    this.reader = recipient;
    if (reading && this.snapshot.mailbox) {
      this.rememberVisible(this.snapshot.mailbox);
      this.emit(this.unreadState(this.snapshot.mailbox));
    }
  }
  private acceptIntent(intent: Intent): void {
    if (this.intent !== intent) return;
    this.intent = null;
    this.emit({ sending: 'idle', operation: null });
    if (intent.kind === 'send') this.options.onAccepted?.(intent.body);
    this.refresh();
  }
  async send(recipient: string, text: string, consent: boolean): Promise<SendOutcome> {
    if (this.intent) return 'uncertain';
    const scope = this.options.getScope();
    if (!this.running || document.hidden || !scope || !this.clock) return 'unavailable';
    try {
      return await this.post({
        kind: 'send',
        body: prepareMessage(scope, recipient, text, consent, this.clock),
      });
    } catch {
      return 'unavailable';
    }
  }
  async sendPublic(text: string, consent: boolean): Promise<SendOutcome> {
    if (this.intent) return 'uncertain';
    const scope = this.options.getScope();
    if (
      !this.running ||
      document.hidden ||
      !scope ||
      !this.clock ||
      this.snapshot.mailbox?.public_available !== true
    )
      return 'unavailable';
    try {
      return await this.post({
        kind: 'send',
        body: preparePublicMessage(scope, text, consent, this.clock),
      });
    } catch {
      return 'unavailable';
    }
  }
  async translate(messageId: string, consent: boolean): Promise<SendOutcome> {
    if (this.intent) return 'uncertain';
    const scope = this.options.getScope();
    if (!this.running || document.hidden || !scope || !this.clock) return 'unavailable';
    try {
      return await this.post({
        kind: 'translate',
        body: prepareTranslation(scope, messageId, consent, this.clock),
      });
    } catch {
      return 'unavailable';
    }
  }
  private async post(intent: Intent): Promise<SendOutcome> {
    this.intent = intent;
    const generation = this.generation;
    const abort = new AbortController();
    this.writeAbort = abort;
    this.emit({ sending: 'sending', operation: intent.kind });
    try {
      const value = await this.options.request(writeEndpoint(intent), intent.body, abort.signal);
      if (!this.ownsIntent(generation, intent)) return 'unavailable';
      const ack = messageAck.safeParse(value);
      if (!ack.success || ack.data.id !== intent.body.id) throw new Error('world_message_ack');
      if (ack.data.status === 'uncertain') {
        this.emit({ sending: 'uncertain' });
        return 'uncertain';
      }
      this.acceptIntent(intent);
      return 'accepted';
    } catch (error) {
      if (!this.ownsIntent(generation, intent)) return 'unavailable';
      const rejected = definitive(error);
      if (rejected) this.intent = null;
      this.emit({ sending: rejected ? 'rejected' : 'uncertain' });
      if (error instanceof ApiError && [401, 403].includes(error.status))
        this.options.onRevoked?.();
      return rejected ? 'rejected' : 'uncertain';
    } finally {
      if (this.writeAbort === abort) this.writeAbort = null;
    }
  }
  async check(): Promise<boolean> {
    const intent = this.intent;
    const scope = this.options.getScope();
    if (!intent || !scope || !this.running || this.writeAbort) return false;
    const generation = this.generation;
    const abort = new AbortController();
    this.writeAbort = abort;
    try {
      const value = await this.options.request(
        '/world/messages/status',
        { ...scope, id: intent.body.id },
        abort.signal
      );
      if (!this.owned(generation, scope) || this.intent !== intent) return false;
      const ack = messageAck.safeParse(value);
      if (!ack.success || ack.data.id !== intent.body.id || ack.data.status === 'uncertain')
        return false;
      this.acceptIntent(intent);
      return true;
    } catch {
      return false;
    } finally {
      if (this.writeAbort === abort) this.writeAbort = null;
    }
  }
  discard(): void {
    this.writeAbort?.abort();
    this.writeAbort = null;
    this.intent = null;
    this.emit({ sending: 'idle', operation: null });
  }
  stop(): void {
    this.running = false;
    this.generation++;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.readAbort?.abort();
    this.writeAbort?.abort();
    this.readAbort = this.writeAbort = null;
    this.clock = this.intent = null;
    this.seen.clear();
    this.viewing = false;
    this.reader = null;
    this.snapshot = emptyState();
    document.removeEventListener('visibilitychange', this.visibility);
  }
}
