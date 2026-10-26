import type { WorldParticipant } from './useWorldSession';
import type { WorldMessage } from './message-protocol';

export interface WorldConversation {
  id: string;
  alias: string;
  online: boolean;
  ambiguous: boolean;
  unread: number;
  hasDraft: boolean;
  latest?: WorldMessage;
  preview: string | null;
}

/** Private mailbox projection: public person IDs, never display names, own a thread. */
export function conversationDirectory(
  participants: readonly WorldParticipant[],
  messages: readonly WorldMessage[],
  unread: Readonly<Record<string, number>>,
  drafts: Readonly<Record<string, string>>,
  aliases: Readonly<Record<string, string>> = {}
): WorldConversation[] {
  const people = new Map(participants.map(person => [person.id, person]));
  const rows = new Map<string, WorldConversation>();
  const add = (id: string, alias: string) => {
    if (!rows.has(id))
      rows.set(id, {
        id,
        alias: people.get(id)?.alias ?? alias,
        online: people.has(id),
        ambiguous: false,
        unread: unread[id] ?? 0,
        hasDraft: Boolean(drafts[id]?.trim()),
        preview: null,
      });
    return rows.get(id)!;
  };
  for (const person of participants) add(person.id, person.alias);
  for (const message of messages) {
    const row = add(
      message.outgoing ? message.recipient_id : message.sender_id,
      message.outgoing ? message.recipient_alias : message.sender_alias
    );
    if (!row.latest || message.created_at >= row.latest.created_at) {
      row.latest = message;
      if (!people.has(row.id))
        row.alias = message.outgoing ? message.recipient_alias : message.sender_alias;
      row.preview = message.text;
    }
  }
  for (const [id, draft] of Object.entries(drafts)) {
    if (draft.trim() && aliases[id]) add(id, aliases[id]);
  }
  const duplicateNames = new Map<string, number>();
  for (const row of rows.values())
    duplicateNames.set(row.alias, (duplicateNames.get(row.alias) ?? 0) + 1);
  return [...rows.values()]
    .map(row => ({
      ...row,
      ambiguous: (duplicateNames.get(row.alias) ?? 0) > 1,
    }))
    .sort(
      (a, b) =>
        Number(b.unread > 0) - Number(a.unread > 0) ||
        (b.latest?.created_at ?? 0) - (a.latest?.created_at ?? 0) ||
        a.alias.localeCompare(b.alias) ||
        a.id.localeCompare(b.id)
    );
}
