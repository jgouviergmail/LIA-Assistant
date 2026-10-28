import { EMOTE_SECONDS, type EmoteKind } from './emote-catalogue';
export interface VisualEmote {
  kind: EmoteKind;
  serial: number;
  started: number;
  until: number;
}
interface Event {
  emote: EmoteKind;
  serial: number;
  expires_at: number;
}

/** Server deadlines become one absolute simulation interval; snapshots never restart it. */
export class EmoteTimeline {
  private events = new Map<string, VisualEmote>();
  get size(): number {
    return this.events.size;
  }
  clear(): void {
    this.events.clear();
  }
  receive(
    id: string,
    event: Event | null | undefined,
    serverTime: number,
    now: number
  ): VisualEmote | null {
    if (!event || !Number.isFinite(serverTime + now) || event.expires_at <= serverTime) return null;
    const old = this.events.get(id);
    if (old && event.serial <= old.serial)
      return event.serial === old.serial && old.until > now ? old : null;
    const until = now + Math.min(EMOTE_SECONDS, event.expires_at - serverTime);
    const visual = {
      kind: event.emote,
      serial: event.serial,
      started: until - EMOTE_SECONDS,
      until,
    };
    if (this.events.size >= 128) this.events.delete(this.events.keys().next().value ?? '');
    this.events.set(id, visual);
    return visual;
  }
}
