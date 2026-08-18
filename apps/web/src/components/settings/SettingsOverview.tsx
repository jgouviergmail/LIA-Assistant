'use client';

/**
 * SettingsOverview — the landing pane of the master-detail settings shell.
 *
 * Shown when no section is selected (desktop; on phones the rail itself is
 * the landing). Every visible section appears as a card with its icon, title
 * and description — the descriptions the accordion page never surfaced —
 * under real `SettingsGroupLabel` headings, which own the page outline (the
 * rail's labels are deliberately not headings).
 *
 * ## The status line
 *
 * A hub that only says what a section IS makes the reader open sections to
 * find out what they hold. So each card that HAS an answer carries one: the
 * exact tally the capability map already resolves, in the same words the
 * capability list uses (`activeLabel`) — two surfaces describing one
 * capability must never phrase it differently.
 *
 * Three properties keep that honest:
 *
 *   - **one request, not thirty.** The whole hub reads a single aggregate
 *     (`/capabilities`), the endpoint that already answers "what can this
 *     account do". Wiring each card to its own section's endpoint would put
 *     thirty requests back on the landing path the shell just cleared;
 *   - **silence beats a guess.** While the aggregate is in flight, or when it
 *     failed, or for a section it says nothing about (a theme, an export, an
 *     admin panel), the card says nothing. A card reading "to set up" during
 *     the first load would accuse an account of being empty before anything
 *     had been counted;
 *   - **the line is not the button's name.** It is `aria-hidden`: the
 *     accessible name stays the destination, and the tally is context the
 *     card shows rather than something the control is called.
 */

import type { TFunction } from 'i18next';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useCapabilities, type CapabilityNode } from '@/hooks/useCapabilities';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { activeLabel } from '@/components/capabilities/capability-state';
import { capabilityOfSection } from '@/lib/capability-sections';
import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import type { SettingsShellTab } from '@/lib/settings-shell-model';
import { cn } from '@/lib/utils';

import { SettingsGroupLabel } from './SettingsGroupLabel';

export interface SettingsOverviewProps {
  lng: Language;
  /** Output of `buildSettingsShellModel` for this user. */
  model: SettingsShellTab[];
  onSelect: (token: SettingsSectionToken) => void;
  /** Rendered above the groups — the portrait shortcut card lives here. */
  children?: React.ReactNode;
}

/**
 * The one line under a card's description, or nothing.
 *
 * Same convention as the constellation it quotes: a filled dot for a live
 * capability, an outlined one for a dormant capability — the reader meets the
 * same two shapes on both surfaces.
 */
function SectionStatus({ node, t }: { node: CapabilityNode; t: TFunction }) {
  return (
    <span
      className="mt-1.5 flex items-center gap-1.5 text-[11px] leading-tight"
      aria-hidden="true"
    >
      <span
        className={cn(
          'h-1.5 w-1.5 shrink-0 rounded-full',
          node.active ? 'bg-primary' : 'border border-muted-foreground'
        )}
      />
      <span className={cn('truncate', node.active ? 'text-primary' : 'text-muted-foreground')}>
        {activeLabel(t, node)}
      </span>
    </span>
  );
}

export function SettingsOverview({ lng, model, onSelect, children }: SettingsOverviewProps) {
  const { t } = useTranslation(lng);
  // Below `lg` this whole pane is CSS-hidden (the rail is the phone landing),
  // so the aggregate is not read at all there — same media query the
  // constellation uses for the same decision.
  const wide = useMediaQuery('(min-width: 1024px)');
  const { nodes, firstLoad, error } = useCapabilities({ enabled: wide });
  // Derived from the payload, never from `loading`: a refetch must not blank
  // thirty status lines the reader is looking at.
  const statusOf = new Map<string, CapabilityNode>(
    firstLoad || error ? [] : (nodes ?? []).map(node => [node.key, node])
  );

  return (
    <div className="space-y-2">
      {children}
      {model.map(tab =>
        tab.groups.map(group => (
          <section key={`${tab.tab}-${group.key}`}>
            <SettingsGroupLabel label={t(`settings.groups.${group.key}`)} />
            <ul className="grid grid-cols-1 gap-3 pb-4 sm:grid-cols-2 xl:grid-cols-3">
              {group.sections.map(section => {
                const Icon = SETTINGS_SECTION_ICONS[section.token];
                const capability = capabilityOfSection(section.token);
                const node = capability ? statusOf.get(capability) : undefined;
                return (
                  <li key={section.token} className="min-w-0">
                    <button
                      type="button"
                      onClick={() => onSelect(section.token)}
                      className="flex h-full w-full items-start gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    >
                      <span className="flex shrink-0 rounded-lg bg-primary/10 p-2">
                        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold leading-tight">
                          {t(section.titleKey)}
                        </span>
                        {/* No `block` beside `line-clamp-2`: both set `display`, and `block`
                            won — the clamp was inert and one long description
                            (haptics) inflated its whole grid row. Measured in the
                            browser, 2026-08-18. */}
                        <span className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {t(section.descriptionKey)}
                        </span>
                        {node && <SectionStatus node={node} t={t} />}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
