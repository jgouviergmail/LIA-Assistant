'use client';

import { Sparkles } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';

/**
 * One switch per thing a reader may refuse to be interrupted by.
 *
 * Extracted from `HeartbeatSourceSwitches` when the anticipated moments needed
 * the same list for a second vocabulary (ADR-281). The shape is identical; what
 * differs is data, so everything that differs is passed as data rather than as
 * a flag the component branches on.
 *
 * Four properties were paid for in production and must survive any change here:
 *
 * - **unavailable is not refused.** Something this account cannot produce still
 *   renders ON, with a note. Greying it out would tell the reader they had
 *   turned it off.
 * - **a note is a fact ABOUT the item, never part of the control's name.** Both
 *   notes sit outside the `<label>` and are attached through `aria-describedby`,
 *   or a screen reader announces "Tasks Not connected" as the switch's own
 *   state.
 * - **the write is a FULL replacement, sorted.** A partial diff lets two
 *   clients disagree about the set; an unstable order makes every save look
 *   like a change.
 * - **the in-flight guard is the handler, not the attribute.** `aria-disabled`
 *   keeps the tab stop; `disabled` would move focus out from under the reader
 *   mid-interaction.
 */
export interface RefusalSwitchesProps {
  /** Every item, in display order — server-published, never re-declared here. */
  items: string[];
  /** Items the reader currently refuses. */
  refused: string[];
  /**
   * Items this account cannot currently produce.
   *
   * Empty for a vocabulary where the notion does not apply: a kind of moment is
   * not something one connects to.
   */
  unavailable?: string[];
  /**
   * What each item is still WAITING for, already narrowed to what is missing.
   *
   * Narrowed by the caller on purpose: "missing" means a refused sibling for
   * one vocabulary and an absent connector for the other, and a component that
   * decided which would be a second authority on both.
   */
  unmetRequirements?: Record<string, string[]>;
  /** Display name of an item. */
  labelFor: (item: string) => string;
  /** Display name of a requirement, for the waiting note. */
  requirementLabelFor?: (requirement: string) => string;
  /** Note rendered under an unavailable item. */
  unavailableNote?: string;
  /** Note rendered under an item whose requirements are unmet. */
  requiresNote?: (requirements: string[]) => string;
  /** Icon per item; anything unlisted renders with a neutral glyph. */
  icons?: Record<string, LucideIcon>;
  /** Prefix of the generated DOM ids — one per vocabulary, so they cannot collide. */
  idPrefix: string;
  /** True while a write is in flight. */
  updating: boolean;
  /** Receives the FULL replacement refusal set. */
  onChange: (refused: string[]) => void;
}

/** What one row needs to render, decided once and away from the JSX. */
interface RowState {
  id: string;
  permitted: boolean;
  missing: string[];
  showsUnavailable: boolean;
  showsRequires: boolean;
  describedBy: string | undefined;
}

/**
 * Resolve one item's row state.
 *
 * Pure, and outside the component, so the list stays a list: the four notes
 * and their `aria-describedby` are decided here rather than inlined in the
 * JSX, where they made the render a hotspot the complexity ratchet refuses.
 */
function rowState(
  item: string,
  options: {
    refused: Set<string>;
    unavailable: Set<string>;
    unmetRequirements?: Record<string, string[]>;
    idPrefix: string;
    hasUnavailableNote: boolean;
    hasRequiresNote: boolean;
  }
): RowState {
  const id = `${options.idPrefix}-${item}`;
  const missing = options.unmetRequirements?.[item] ?? [];
  const showsUnavailable = options.unavailable.has(item) && options.hasUnavailableNote;
  const showsRequires = missing.length > 0 && options.hasRequiresNote;
  // Built from the notes actually rendered rather than from one test: an item
  // can legitimately carry both at once.
  const describedBy =
    [showsUnavailable ? `${id}-note` : null, showsRequires ? `${id}-requires` : null]
      .filter(Boolean)
      .join(' ') || undefined;
  return {
    id,
    permitted: !options.refused.has(item),
    missing,
    showsUnavailable,
    showsRequires,
    describedBy,
  };
}

export function RefusalSwitches({
  items,
  refused,
  unavailable,
  unmetRequirements,
  labelFor,
  requirementLabelFor,
  unavailableNote,
  requiresNote,
  icons,
  idPrefix,
  updating,
  onChange,
}: RefusalSwitchesProps) {
  const refusedSet = new Set(refused);
  const unavailableSet = new Set(unavailable ?? []);

  const toggle = (item: string) => {
    // The guard, not the attribute, is what prevents the double submit.
    if (updating) return;
    const next = new Set(refusedSet);
    if (next.has(item)) next.delete(item);
    else next.add(item);
    onChange([...next].sort());
  };

  return (
    <div className="space-y-2">
      {items.map(item => {
        const state = rowState(item, {
          refused: refusedSet,
          unavailable: unavailableSet,
          unmetRequirements,
          idPrefix,
          hasUnavailableNote: Boolean(unavailableNote),
          hasRequiresNote: Boolean(requiresNote),
        });
        return (
          <div
            key={item}
            className={cn(
              'flex items-center gap-3 rounded-lg border border-border/40 bg-card/40 px-3 py-2',
              'transition-colors',
              state.permitted ? 'text-foreground' : 'text-muted-foreground'
            )}
          >
            <RowIcon icon={icons?.[item]} permitted={state.permitted} />
            {/* `min-w-0` so a long localized label truncates instead of pushing
                the switch off a 320 px screen. */}
            <div className="min-w-0 flex-1">
              <Label htmlFor={state.id} className="block cursor-pointer truncate text-sm">
                {labelFor(item)}
              </Label>
              {state.showsUnavailable && (
                <span
                  id={`${state.id}-note`}
                  className="block truncate text-xs text-muted-foreground"
                >
                  {unavailableNote}
                </span>
              )}
              {state.showsRequires && (
                // Not truncated: this one names OTHER controls on the same
                // screen, and a reader who cannot read which ones is left
                // exactly where they started.
                <span id={`${state.id}-requires`} className="block text-xs text-warning">
                  {requiresNote?.(
                    state.missing.map(name => requirementLabelFor?.(name) ?? name)
                  )}
                </span>
              )}
            </div>
            <Switch
              id={state.id}
              checked={state.permitted}
              onCheckedChange={() => toggle(item)}
              aria-disabled={updating || undefined}
              aria-describedby={state.describedBy}
            />
          </div>
        );
      })}
    </div>
  );
}

/** The item's glyph. Anything unlisted renders with a neutral one. */
function RowIcon({ icon, permitted }: { icon?: LucideIcon; permitted: boolean }) {
  const Icon = icon ?? Sparkles;
  return (
    <span
      className={cn(
        'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
        permitted ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
      )}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </span>
  );
}
