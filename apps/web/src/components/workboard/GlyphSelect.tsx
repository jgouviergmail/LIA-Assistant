'use client';
/**
 * A list whose every item is a glyph, then a word (ADR-276, D79).
 *
 * The column and the holder of a ticket are chosen from lists a board is
 * SCANNED by — the column's mark is on its header and on the settings chips,
 * the holder's on the card's badge — and the owner asked for those marks on
 * the items themselves (2026-09-10). A native `<option>` holds nothing but
 * text, so the two lists left the native `<select>` for the application's own
 * listbox, through this ONE component. Every list of the workboard is one
 * of its vocabularies — `StatusSelect`, `HolderSelect`, `PrioritySelect`,
 * the execution mode, the three filters (D81) — and shares every mechanic
 * below. A field of the filter bar also wears its FAMILY glyph in the
 * label: `GlyphLabel`, shared with the search field beside those lists.
 *
 * - The closed trigger reflects the chosen item, glyph included — Radix
 *   mirrors the item's text node into the value.
 * - A press or a key on the trigger never reaches an ancestor: the list was
 *   born on a card that can be a sortable item, and a drag listener above
 *   would swallow the press whole. Radix composes its own handlers after ours
 *   and opens all the same.
 * - A gesture that STARTS inside the open list belongs to the list: the React
 *   tree runs through the portal, so without this a swipe across an item
 *   would reach the board's column swipe underneath (`Board`).
 */
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

export interface GlyphItem {
  value: string;
  /** Its mark, `aria-hidden` — the word beside it always says the same thing. */
  glyph: React.ReactNode;
  text: string;
  /**
   * Shown, never takeable.
   *
   * For the one item a list may carry without offering: the CURRENT value,
   * when it is not one of the choices — a holder whose connections have not
   * loaded yet. Without it the trigger renders empty; offered plainly, it is
   * a choice the server can only refuse.
   */
  disabled?: boolean;
}

export interface GlyphSelectProps {
  value: string;
  /** The accessible name — a card in a list needs to say WHICH ticket. */
  label: string;
  /** The family's glyph, drawn in the visible label; meaningless when hidden. */
  labelGlyph?: React.ReactNode;
  items: readonly GlyphItem[];
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
  /** Visually hide the label; it stays in the accessibility tree. */
  hideLabel?: boolean;
  id?: string;
}

function keep(event: React.SyntheticEvent): void {
  event.stopPropagation();
}

/**
 * A field's label, with the mark that lets the row be scanned. The shared
 * `Label`, never a raw `<label>` with copied classes: it carries
 * `leading-none`, and a hand-written twin half a line taller is exactly
 * what put a control out of line with the field beside it.
 */
export function GlyphLabel({
  htmlFor,
  glyph,
  children,
}: {
  htmlFor?: string;
  glyph?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Label htmlFor={htmlFor} className={glyph ? 'flex items-center gap-1.5' : undefined}>
      {glyph}
      {children}
    </Label>
  );
}

export function GlyphSelect({
  value,
  label,
  labelGlyph,
  items,
  onChange,
  disabled,
  className,
  hideLabel = true,
  id,
}: GlyphSelectProps) {
  return (
    <>
      {hideLabel ? null : (
        <GlyphLabel htmlFor={id} glyph={labelGlyph}>
          {label}
        </GlyphLabel>
      )}
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger
          id={id}
          aria-label={hideLabel ? label : undefined}
          className={cn('h-8 px-2 text-xs', className)}
          onPointerDown={keep}
          onKeyDown={keep}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent onTouchStart={keep} onTouchEnd={keep}>
          {items.map(item => (
            <SelectItem key={item.value} value={item.value} disabled={item.disabled}>
              <span className="inline-flex items-center gap-2">
                {item.glyph}
                {item.text}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </>
  );
}
