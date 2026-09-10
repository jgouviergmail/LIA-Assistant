'use client';
/**
 * Who holds a ticket, as a control (ADR-276, D77, D79).
 *
 * The owner may hand a ticket to anybody they are connected to, to LIA, or
 * take it back. ONE component for the panel's field and for a card where
 * nothing drags (a phone, lot 19): the two must never offer two different
 * sets of holders. The application's own listbox, like `StatusSelect` and for
 * the same reason (lot 20): each holder wears the glyph the card's badge
 * already gives it — the spark, the person, the two people — before the name.
 *
 * A holder who is not the owner gets no list at all: the service lets them
 * hand the ticket BACK and nothing else, and a menu whose every entry but one
 * is refused is a question with one answer — the panel offers the return as
 * a button instead.
 */
import { useTranslation } from 'react-i18next';

import { GlyphSelect, type GlyphItem } from '@/components/workboard/GlyphSelect';
import type { PeerName } from '@/lib/workboard/display';
import { partyIcon } from '@/lib/workboard/icons';

export interface HolderSelectProps {
  /** `me`, `lia` or a peer id — what `heldBy` returns. */
  value: string;
  peers: readonly PeerName[];
  /** The accessible name — a card in a list needs to say WHICH ticket. */
  label: string;
  /** The choice, as `assignPatch` reads it. */
  onChange: (choice: string) => void;
  /** Visually hide the label; it stays in the accessibility tree. */
  hideLabel?: boolean;
  id?: string;
  className?: string;
}

/** The badge's glyph, at the size of the line it sits on. */
const GLYPH = 'h-3.5 w-3.5 shrink-0';

export function HolderSelect({
  value,
  peers,
  label,
  onChange,
  hideLabel = true,
  id,
  className,
}: HolderSelectProps) {
  const { t } = useTranslation();
  const items: GlyphItem[] = [
    { value: 'me', glyph: partyIcon('me', GLYPH), text: t('workboard.party.me') },
    { value: 'lia', glyph: partyIcon('lia', GLYPH), text: t('workboard.party.lia') },
    ...peers.map(peer => ({
      value: peer.peer_id,
      glyph: partyIcon('peer', GLYPH),
      text: peer.peer_display_name,
    })),
  ];
  // A holder the list cannot name — the connections are still in flight, or
  // one has just gone — is named « somebody else » rather than left blank:
  // a listbox whose value matches no item renders an EMPTY trigger, right
  // under a badge that says the ticket is held. `assigneeParty` already
  // resolves the same id to `unknown` for that badge; this keeps the two
  // reading alike. Last, and only because it IS the current value.
  if (!items.some(item => item.value === value)) {
    items.push({
      value,
      glyph: partyIcon('unknown', GLYPH),
      text: t('workboard.party.unknown'),
      // Shown, never takeable: choosing it would send an id the server does
      // not accept, and it is the value already in force anyway.
      disabled: true,
    });
  }
  return (
    <GlyphSelect
      id={id}
      label={label}
      hideLabel={hideLabel}
      value={value}
      items={items}
      className={className}
      onChange={onChange}
    />
  );
}
