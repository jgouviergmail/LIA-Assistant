import { useState } from 'react';
import { PUBLIC_THREAD } from './public-message-protocol';
import type { WorldParticipant } from './useWorldSession';

export const AUTOMATIC_RECIPIENT = '@auto';
const PUBLIC = { id: PUBLIC_THREAD, alias: '' };

/** Pin the address, never move a draft between audiences as the world moves. */
export function useCompactRecipient(
  nearest: WorldParticipant | undefined,
  drafts: Readonly<Record<string, string>>,
  busy: boolean
) {
  const [choice, setChoice] = useState<{
    person: WorldParticipant;
    manual: boolean;
    focused: boolean;
  } | null>(null);
  const pinned = choice && (choice.manual || choice.focused || drafts[choice.person.id] || busy);
  const person = pinned ? choice.person : (nearest ?? PUBLIC);
  return {
    person,
    value: choice?.manual ? choice.person.id : AUTOMATIC_RECIPIENT,
    hold() {
      setChoice(current => ({
        person,
        manual: current?.manual ?? false,
        focused: current?.focused ?? false,
      }));
    },
    focus() {
      setChoice(current => ({ person, manual: current?.manual ?? false, focused: true }));
    },
    blur() {
      setChoice(current => current && { ...current, focused: false });
    },
    select(selected: WorldParticipant | null) {
      if (busy) return;
      setChoice(selected ? { person: selected, manual: true, focused: true } : null);
    },
  };
}
