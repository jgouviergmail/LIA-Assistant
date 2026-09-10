/**
 * The glyphs the board is scanned by (ADR-276).
 *
 * A column header, a filter label, a card badge and an item of the two lists
 * a ticket is moved with are all read at a glance before they are read as
 * words. One map per family, here rather than beside each component, so a
 * column and the filter that narrows to it — or a holder's badge and the
 * list that offers that holder — can never end up wearing two different
 * marks for one idea.
 *
 * Each helper returns an ELEMENT, never a component type. Binding a component
 * to a capitalised local during render creates a component on every pass —
 * React resets its state, and the repository's `react-hooks/static-components`
 * ratchet refuses it.
 *
 * Every glyph is `aria-hidden`: the word beside it always says the same thing,
 * so nothing is carried by shape or colour alone.
 */
import {
  ArrowUpDown,
  Asterisk,
  CalendarClock,
  CalendarPlus,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  ChevronsUp,
  CircleCheck,
  CircleHelp,
  ShieldQuestion,
  CircleDashed,
  Flag,
  History,
  Lightbulb,
  ListOrdered,
  LoaderCircle,
  Minus,
  PauseCircle,
  Search,
  Sparkles,
  User,
  Users,
  Workflow,
  Zap,
} from 'lucide-react';

import { priorityInk } from '@/lib/status-tone';
import { cn } from '@/lib/utils';
import type { PartyLabel } from '@/lib/workboard/display';

/**
 * The mark of a column.
 *
 * Args:
 *   status: A column key.
 *   className: Sizing and colour, decided by the caller.
 *
 * Returns:
 *   Its glyph — the neutral « not started » circle for a column this build
 *   does not know, so a header never loses its alignment.
 */
export function columnIcon(status: string, className: string): React.ReactNode {
  const shared = { className, 'aria-hidden': true } as const;
  switch (status) {
    case 'idea':
      return <Lightbulb {...shared} />;
    case 'in_progress':
      return <LoaderCircle {...shared} />;
    case 'waiting':
      return <PauseCircle {...shared} />;
    case 'confirming':
      return <ShieldQuestion {...shared} />;
    case 'validating':
      return <CheckCheck {...shared} />;
    case 'done':
      return <CircleCheck {...shared} />;
    default:
      return <CircleDashed {...shared} />;
  }
}

/**
 * The mark of a party — who holds or owns a ticket.
 *
 * « Moi », « LIA » and a peer's first name are three words of the same weight
 * in the same grey pill, and telling them apart meant reading each one. The
 * glyph carries the KIND and the word keeps saying WHO. One map for the
 * card's badge and for the holder list (lot 20): a list whose « LIA » wore a
 * different mark from the badge above it would be two vocabularies for one
 * idea. Every PERSON wears the theme colour, LIA's spark and a human alike
 * (owner, 2026-09-10 — D82), whatever the caller sizes it to; `unknown` is
 * not a person and stays neutral.
 *
 * Args:
 *   kind: `lia`, `me`, `peer` or `unknown`.
 *   className: Sizing, decided by the caller.
 *
 * Returns:
 *   Its glyph.
 */
export function partyIcon(kind: PartyLabel['kind'], className: string): React.ReactNode {
  const person = cn(className, 'text-primary');
  switch (kind) {
    case 'lia':
      return <Sparkles className={person} aria-hidden="true" />;
    case 'me':
      return <User className={person} aria-hidden="true" />;
    case 'peer':
      return <Users className={person} aria-hidden="true" />;
    case 'unknown':
      return <CircleHelp className={className} aria-hidden="true" />;
  }
}

/**
 * The mark of a priority — RANKED, so four items read as a ladder before
 * they are read as words, in the ink of the edge that ranks the card
 * (`priorityInk`, declared beside `priorityAccent`).
 *
 * Args:
 *   priority: `low`, `medium`, `high` or `urgent`.
 *   className: Sizing, decided by the caller; the ink is the priority's.
 *
 * Returns:
 *   Its glyph; the level mark for anything unknown.
 */
export function priorityIcon(priority: string, className: string): React.ReactNode {
  const shared = { className: cn(className, priorityInk(priority)), 'aria-hidden': true } as const;
  switch (priority) {
    case 'urgent':
      return <ChevronsUp {...shared} />;
    case 'high':
      return <ChevronUp {...shared} />;
    case 'low':
      return <ChevronDown {...shared} />;
    default:
      return <Minus {...shared} />;
  }
}

/**
 * The mark of an execution mode — the chat header toggle's own
 * (`execution-mode-toggle`): the same words, the same signs.
 *
 * Args:
 *   mode: `pipeline` or `react`.
 *   className: Sizing and colour, decided by the caller.
 *
 * Returns:
 *   Its glyph; the loop's for anything unknown, the loop being the default.
 */
export function modeIcon(mode: string, className: string): React.ReactNode {
  const shared = { className, 'aria-hidden': true } as const;
  return mode === 'pipeline' ? <Workflow {...shared} /> : <Zap {...shared} />;
}

/**
 * The mark of a sort order.
 *
 * Args:
 *   sort: `position`, `priority`, `due`, `updated` or `created`.
 *   className: Sizing and colour, decided by the caller.
 *
 * Returns:
 *   Its glyph; the family's for anything unknown.
 */
export function sortIcon(sort: string, className: string): React.ReactNode {
  const shared = { className, 'aria-hidden': true } as const;
  switch (sort) {
    case 'position':
      return <ListOrdered {...shared} />;
    case 'priority':
      return <Flag {...shared} />;
    case 'due':
      return <CalendarClock {...shared} />;
    case 'updated':
      return <History {...shared} />;
    case 'created':
      return <CalendarPlus {...shared} />;
    default:
      return <ArrowUpDown {...shared} />;
  }
}

/**
 * The mark of « any » — « tout le monde », « toute priorité »: ONE sign for
 * one idea, whatever the filter.
 *
 * Args:
 *   className: Sizing and colour, decided by the caller.
 *
 * Returns:
 *   Its glyph.
 */
export function anyIcon(className: string): React.ReactNode {
  return <Asterisk className={className} aria-hidden="true" />;
}

/**
 * The mark of a filter field.
 *
 * Args:
 *   field: `search`, `side`, `priority` or `sort`.
 *   className: Sizing and colour, decided by the caller.
 *
 * Returns:
 *   Its glyph; the search glyph for anything unknown.
 */
export function filterIcon(field: string, className: string): React.ReactNode {
  const shared = { className, 'aria-hidden': true } as const;
  switch (field) {
    case 'side':
      return <User {...shared} />;
    case 'priority':
      return <Flag {...shared} />;
    case 'sort':
      return <ArrowUpDown {...shared} />;
    default:
      return <Search {...shared} />;
  }
}
