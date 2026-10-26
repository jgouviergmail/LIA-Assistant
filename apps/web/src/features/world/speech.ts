/** Owner-local ephemeral presentation. Never serialized to spatial authority or storage. */
import type { Notification } from '@/hooks/useNotifications';
import type { WorldMailbox } from './message-protocol';
import type { Simulation } from './simulation';
import { conversationRoute } from './social-approach';

export interface SpeechDelivery {
  id: string;
  speaker: string;
  label: string;
  text: string | null;
  ready: boolean;
  created: number;
}
export interface SpeechBubble {
  id: string;
  speaker: string;
  label: string;
  text: string;
  kind: 'private' | 'public' | 'lia';
  created: number;
  until: number;
}
const EMPTY: readonly SpeechBubble[] = Object.freeze([]);
const DISPLAY_MS = 5000;
const PENDING_MS = 60000;
const LIMIT = 128;
export function privateSpeechDeliveries(mailbox: WorldMailbox): SpeechDelivery[] {
  return mailbox.messages
    .filter(message => !message.outgoing)
    .map(message => ({
      id: message.id,
      speaker: message.sender_id,
      label: message.sender_alias,
      text: message.text,
      ready: message.status === 'original' || message.status === 'translated',
      created: message.created_at,
    }));
}
/** Public echo is intentional; private outgoing text stays excluded above. */
export function publicSpeechDeliveries(mailbox: WorldMailbox): SpeechDelivery[] {
  return (mailbox.public_messages ?? []).map(message => ({
    id: message.id,
    speaker: message.sender_id,
    label: message.sender_alias,
    text: message.text,
    ready: message.outgoing || message.status === 'original' || message.status === 'translated',
    created: message.created_at,
  }));
}
function remember<T>(map: Map<string, T>, key: string, value: T): void {
  map.delete(key);
  map.set(key, value);
  if (map.size > LIMIT) {
    const first = map.keys().next().value;
    if (first !== undefined) map.delete(first);
  }
}
function recentNotice(notification: Notification, wall: number): boolean {
  const age = wall - notification.timestamp.getTime();
  return Number.isFinite(age) && age >= -5000 && age <= 120000;
}
function noticeKey(notification: Notification): { id: string; stable: boolean } | null {
  const identity = notification.metadata?.message_id ?? notification.metadata?.run_id;
  if (identity !== undefined) {
    if (typeof identity !== 'string' || !identity || identity.length > 256) return null;
    return { id: notification.type + ':' + identity, stable: true };
  }
  // Interest targets are reusable. Only short-window duplicates may share this key.
  return {
    id:
      notification.type +
      ':' +
      notification.id +
      ':' +
      Array.from(notification.content).slice(0, 3000).join(''),
    stable: false,
  };
}
export class WorldSpeech {
  private active = false;
  private proactivePaused = false;
  private seen = new Map<string, boolean>();
  private notices = new Map<string, number>();
  private baselines = new Set<string>();
  private latest = new Map<string, number>();
  private lines = new Map<string, SpeechBubble>();
  private pending: { id: string; text: string; until: number } | null = null;
  private nextApproach = 0;
  private snapshot: readonly SpeechBubble[] = EMPTY;
  private listeners = new Set<() => void>();
  readonly subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  readonly getSnapshot = () => this.snapshot;
  readonly getServerSnapshot = () => EMPTY;
  setActive(value: boolean): void {
    this.active = value;
    if (value) return;
    this.lines.clear();
    this.pending = null;
    this.baselines.clear();
    this.publish(EMPTY);
  }
  setProactivePaused(value: boolean): void {
    this.proactivePaused = value;
  }
  receive(
    deliveries: readonly SpeechDelivery[],
    server: number,
    kind: 'private' | 'public',
    now: number
  ): void {
    if (!this.active || !Number.isFinite(server + now)) return;
    const initial = !this.baselines.has(kind);
    this.baselines.add(kind);
    for (const item of deliveries) this.receiveOne(item, server, kind, now, initial);
  }
  private receiveOne(
    item: SpeechDelivery,
    server: number,
    kind: 'private' | 'public',
    now: number,
    initial: boolean
  ): void {
    const key = kind + ':' + item.id,
      previous = this.seen.get(key);
    remember(this.seen, key, item.ready);
    if (initial || previous === true || !item.ready || !item.text) return;
    if (server - item.created > 60 || item.created > server + 5) return;
    if (item.created < (this.latest.get(item.speaker) ?? -Infinity)) return;
    remember(this.latest, item.speaker, item.created);
    this.show({
      id: item.id,
      speaker: item.speaker,
      label: item.label,
      text: item.text,
      created: item.created,
      kind,
      until: now + DISPLAY_MS,
    });
  }
  private show(bubble: SpeechBubble): void {
    // One bubble per speaker across channels; bounded even through long sessions.
    remember(this.lines, bubble.speaker, Object.freeze(bubble));
  }
  proactive(notification: Notification, now = performance.now(), wall = Date.now()): void {
    if (!this.active || !notification.type.startsWith('proactive_')) return;
    if (!recentNotice(notification, wall)) return;
    const key = noticeKey(notification);
    if (!key) return;
    const previous = this.notices.get(key.id);
    if (previous !== undefined && (key.stable || now - previous < 10000)) return;
    remember(this.notices, key.id, now);
    const text = Array.from(notification.content.trim()).slice(0, 3000).join('');
    if (!text) return;
    this.pending = { id: key.id, text, until: now + PENDING_MS };
    this.nextApproach = 0;
  }
  bubbles(now: number): readonly SpeechBubble[] {
    return this.active ? [...this.lines.values()].filter(line => line.until > now) : EMPTY;
  }
  advance(sim: Simulation, now: number, paused: boolean): void {
    this.expire(now);
    this.presentLia(sim, now, paused);
    const follow = this.active && (this.pending !== null || this.lines.has('lia'));
    if (sim.noticeFollowing !== follow) {
      sim.bip.path = [];
      sim.wait = 0;
    }
    sim.noticeFollowing = follow;
    if (follow && now >= this.nextApproach) {
      this.nextApproach = now + 800;
      // Replan a moving target at a bounded rate through existing navigation.
      if (!conversationRoute(sim, sim.bip.position).length) {
        sim.bip.path = [];
        sim.wait = 0;
      }
    }
    const speakers = new Set(sim.visitors.map(person => person.id));
    if (sim.player.publicId) speakers.add(sim.player.publicId);
    speakers.add('lia');
    this.publish(this.bubbles(now).filter(line => speakers.has(line.speaker)));
  }
  private expire(now: number): void {
    for (const [key, line] of this.lines) if (line.until <= now) this.lines.delete(key);
    if (this.pending && this.pending.until <= now) this.pending = null;
  }
  private presentLia(sim: Simulation, now: number, paused: boolean): void {
    if (!this.active || paused || this.proactivePaused || !this.pending) return;
    if (!conversationRoute(sim, sim.bip.position).length) return;
    const pending = this.pending;
    this.pending = null;
    this.show({
      id: pending.id,
      speaker: 'lia',
      label: 'LIA',
      text: pending.text,
      created: now,
      kind: 'lia',
      until: now + DISPLAY_MS,
    });
  }
  private publish(lines: readonly SpeechBubble[]): void {
    if (
      lines.length === this.snapshot.length &&
      lines.every((line, i) => line === this.snapshot[i])
    )
      return;
    this.snapshot = lines.length ? lines : EMPTY;
    for (const listener of this.listeners) listener();
  }
}
