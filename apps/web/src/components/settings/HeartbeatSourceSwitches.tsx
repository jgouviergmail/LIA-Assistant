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

import { RefusalSwitches } from '@/components/settings/RefusalSwitches';

/**
 * Which sources may INTERRUPT the reader — distinct from which are connected.
 *
 * The panel used to show sources as connected or not, and the only documented
 * way to stop mail-driven nudges was to disconnect the mail connector, which
 * also removes the tool the user asks with. These switches separate
 * "LIA may use this service when I ask" from "LIA may interrupt me from it".
 *
 * The list itself is `RefusalSwitches` (shared with the moment kinds since
 * ADR-281): what is specific here is the vocabulary, the icons, and — the one
 * thing that could not be shared — what "missing" MEANS. For a source it is a
 * SIBLING the reader refused, so the narrowing happens here; for a kind it is
 * an absent connector, which only the server can know.
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
  const unmet: Record<string, string[]> = {};
  for (const [source, requires] of Object.entries(sourceDependencies ?? {})) {
    if (refused.has(source)) continue;
    const missing = requires.filter(required => refused.has(required));
    if (missing.length > 0) unmet[source] = missing;
  }

  return (
    <RefusalSwitches
      items={allSources}
      refused={disabledSources}
      unavailable={allSources.filter(source => !connected.has(source))}
      unmetRequirements={unmet}
      labelFor={source => t(`heartbeat.source_${source}`)}
      requirementLabelFor={source => t(`heartbeat.source_${source}`)}
      unavailableNote={t('heartbeat.source_not_connected')}
      requiresNote={sources => t('heartbeat.source_requires', { sources: sources.join(', ') })}
      icons={SOURCE_ICONS}
      idPrefix="heartbeat-source"
      updating={updating}
      onChange={onChange}
    />
  );
}
