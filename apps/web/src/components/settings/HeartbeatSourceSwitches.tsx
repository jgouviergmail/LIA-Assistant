'use client';

import {
  BookOpen,
  Brain,
  Calendar,
  CakeSlice,
  CloudSun,
  Heart,
  ListChecks,
  ListTodo,
  Mail,
  Navigation,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';

/**
 * Which sources may INTERRUPT the reader — distinct from which are connected.
 *
 * The panel used to show sources as connected or not, and the only documented
 * way to stop mail-driven nudges was to disconnect the mail connector, which
 * also removes the tool the user asks with. These switches separate
 * "LIA may use this service when I ask" from "LIA may interrupt me from it".
 *
 * Two rules the UI must not blur:
 *
 * - **Unavailable is not refused.** A source nobody connected still reads as
 *   permitted, because the reader has decided nothing about it. Showing it off
 *   would state a decision they never made — and connecting the service later
 *   would then silently require a second trip here.
 * - **Busy is not removed.** While a write is in flight the switches carry
 *   `aria-disabled` and the handler guards; `disabled` would blur the focused
 *   control and drop it from the tab order.
 *
 * The vocabulary and its order come from the SERVER (`all_sources`): the
 * client never re-declares the list it does not enforce.
 */
export interface HeartbeatSourceSwitchesProps {
  /** Every toggleable source, in display order (server-published). */
  allSources: string[];
  /** Sources the reader currently refuses. */
  disabledSources: string[];
  /** Sources this account is actually connected to. */
  availableSources: string[];
  /**
   * Sources whose result requires another source, as published by the server.
   *
   * Optional so a response predating the field renders exactly as before —
   * silent, never a warning built from a client-side guess about which source
   * feeds which.
   */
  sourceDependencies?: Record<string, string[]>;
  /** True while a write is in flight. */
  updating: boolean;
  /** Receives the FULL replacement refusal set. */
  onChange: (disabled: string[]) => void;
}

/** Icon per source. An unlisted source still renders, with a neutral glyph. */
const SOURCE_ICONS: Record<string, LucideIcon> = {
  calendar: Calendar,
  emails: Mail,
  tasks: ListChecks,
  weather: CloudSun,
  interests: Sparkles,
  memories: Brain,
  journals: BookOpen,
  health_signals: Heart,
  birthdays: CakeSlice,
  open_loops: ListTodo,
  departure: Navigation,
};

export function HeartbeatSourceSwitches({
  allSources,
  disabledSources,
  availableSources,
  sourceDependencies,
  updating,
  onChange,
}: HeartbeatSourceSwitchesProps) {
  const { t } = useTranslation();
  const refused = new Set(disabledSources);
  const connected = new Set(availableSources);

  /**
   * Dependencies this reader refused, for a source they left ON.
   *
   * Empty when the source is refused too: they turned it off themselves, so
   * there is no surprise left to explain and the warning would be noise.
   */
  const missingFor = (source: string): string[] => {
    if (refused.has(source)) return [];
    return (sourceDependencies?.[source] ?? []).filter(required => refused.has(required));
  };

  const toggle = (source: string) => {
    // The guard, not the attribute, is what prevents the double submit.
    if (updating) return;
    const next = new Set(refused);
    if (next.has(source)) next.delete(source);
    else next.add(source);
    // Full replacement, sorted: the API replaces the set wholesale, and a
    // stable order keeps two equivalent requests identical.
    onChange([...next].sort());
  };

  return (
    <div className="space-y-2">
      {allSources.map(source => {
        const Icon = SOURCE_ICONS[source] ?? Sparkles;
        const permitted = !refused.has(source);
        const id = `heartbeat-source-${source}`;
        const missing = missingFor(source);
        // Both notes are facts ABOUT the source, never part of the control's
        // name — and a source can carry both at once, so the attribute is
        // built from the notes actually rendered rather than from one test.
        const describedBy =
          [
            connected.has(source) ? null : `${id}-note`,
            missing.length > 0 ? `${id}-requires` : null,
          ]
            .filter(Boolean)
            .join(' ') || undefined;
        return (
          <div
            key={source}
            className={cn(
              'flex items-center gap-3 rounded-lg border border-border/40 bg-card/40 px-3 py-2',
              'transition-colors',
              permitted ? 'text-foreground' : 'text-muted-foreground'
            )}
          >
            <span
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                permitted ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
            </span>
            {/* `min-w-0` so a long localized label truncates instead of
                pushing the switch off a 320 px screen.

                The availability note sits OUTSIDE the label and is attached
                through `aria-describedby`: inside it, it would become part of
                the control's accessible NAME ("Tasks Not connected"), which
                reads as a state of the switch rather than a fact about the
                account. */}
            <div className="min-w-0 flex-1">
              <Label htmlFor={id} className="block cursor-pointer truncate text-sm">
                {t(`heartbeat.source_${source}`)}
              </Label>
              {!connected.has(source) && (
                <span id={`${id}-note`} className="block truncate text-xs text-muted-foreground">
                  {t('heartbeat.source_not_connected')}
                </span>
              )}
              {missing.length > 0 && (
                // Not truncated: this one names OTHER switches on the same
                // screen, and a reader who cannot read which ones is left
                // exactly where they started.
                <span id={`${id}-requires`} className="block text-xs text-warning">
                  {t('heartbeat.source_requires', {
                    sources: missing.map(name => t(`heartbeat.source_${name}`)).join(', '),
                  })}
                </span>
              )}
            </div>
            <Switch
              id={id}
              checked={permitted}
              onCheckedChange={() => toggle(source)}
              aria-disabled={updating || undefined}
              aria-describedby={describedBy}
            />
          </div>
        );
      })}
    </div>
  );
}
