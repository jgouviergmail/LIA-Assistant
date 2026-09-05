'use client';

import Link from 'next/link';
import { ChevronRight, ClipboardList, HelpCircle, Settings, Sparkles } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/**
 * Quick access to Help, the constellation, the registers and Settings — a
 * compact bar above the briefing.
 *
 * These are SECONDARY destinations sitting right before the day's content. As
 * large cards they would cost the briefing its vertical space; one bar says the
 * same thing compactly, with nothing removed.
 *
 * Relations used to sit here because it had no nav slot. It has one now
 * (`lib/dashboard-nav.ts`), so the tile was a second door to the same room —
 * removed 2026-09-04. A destination reachable from the header does not also
 * need a tile: two doors make the bar longer without making anything more
 * reachable.
 *
 * Layout is decided by MEASUREMENT: the segments STACK below `sm` (full-width
 * rows, every locale legible) and sit side by side above it. Four quarters at
 * `sm` (640 px) leave ~160 px each; the tight two-up-at-320 px case never
 * occurs because 320 px is below `sm`, where they stack.
 *
 * Links, not buttons: these are navigations. `<Link>` gives middle-click,
 * open-in-new-tab, the URL on hover and the "link" role — matching the rest of
 * the dashboard (`BriefingSetupHint`, the briefing cards).
 */
export interface QuickAccessCompactProps {
  /** Current URL locale segment. */
  lng: string;
}

export function QuickAccessCompact({ lng }: QuickAccessCompactProps) {
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-2xl border bg-card sm:flex-row',
        'divide-y divide-border sm:divide-x sm:divide-y-0',
        'shadow-[var(--lia-shadow-sm)]'
      )}
    >
      <QuickAccessAction
        href={`/${lng}/dashboard/faq`}
        icon={HelpCircle}
        label={t('dashboard.quick_access_compact.help')}
        sublabel={t('dashboard.quick_access_compact.help_sub')}
        tone="primary"
      />
      {/* The constellation earns a door here rather than a sixth nav slot:
          the header row is already at its widest (six destinations, icons only
          below `xl`), and this is a place you visit, not a place you live. */}
      <QuickAccessAction
        href={`/${lng}/dashboard/capabilities`}
        icon={Sparkles}
        label={t('dashboard.quick_access_compact.capabilities')}
        sublabel={t('dashboard.quick_access_compact.capabilities_sub')}
        tone="primary"
      />
      {/* ADR-263: the register of what LIA actually did. It earns a door here
          for the same reason the constellation does — a place you visit to
          check something, not a place you live. */}
      <QuickAccessAction
        href={`/${lng}/dashboard/actions`}
        icon={ClipboardList}
        label={t('dashboard.quick_access_compact.actions')}
        sublabel={t('dashboard.quick_access_compact.actions_sub')}
        tone="success"
      />
      <QuickAccessAction
        href={`/${lng}/dashboard/settings`}
        icon={Settings}
        label={t('dashboard.quick_access_compact.settings')}
        sublabel={t('dashboard.quick_access_compact.settings_sub')}
        tone="warning"
      />
    </div>
  );
}

/** Per-tone classes. Kept as whole literals so Tailwind can see them. */
const TONE_CLASSES = {
  primary: { badge: 'bg-primary/10 text-primary', hover: 'hover:bg-primary/5' },
  success: { badge: 'bg-success/10 text-success', hover: 'hover:bg-success/5' },
  warning: { badge: 'bg-warning/10 text-warning', hover: 'hover:bg-warning/5' },
} as const;

interface QuickAccessActionProps {
  href: string;
  icon: LucideIcon;
  label: string;
  sublabel: string;
  tone: keyof typeof TONE_CLASSES;
}

function QuickAccessAction({ href, icon: Icon, label, sublabel, tone }: QuickAccessActionProps) {
  const toneClasses = TONE_CLASSES[tone];

  return (
    <Link
      href={href}
      className={cn(
        'group flex min-h-14 flex-1 items-center gap-3 px-4 py-3 transition-colors',
        // `ring-inset`: the bar clips its children, so an offset ring would be
        // cut off on the segment that touches the border.
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
        toneClasses.hover
      )}
    >
      <span
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
          toneClasses.badge
        )}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      {/* `min-w-0` is load-bearing: without it the flex item refuses to shrink
          below its intrinsic text width and the chevron is pushed out. */}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-foreground">{label}</span>
        <span className="block truncate text-xs text-muted-foreground">{sublabel}</span>
      </span>
      <ChevronRight
        className={cn(
          'h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200',
          'motion-safe:group-hover:translate-x-0.5'
        )}
        aria-hidden="true"
      />
    </Link>
  );
}
