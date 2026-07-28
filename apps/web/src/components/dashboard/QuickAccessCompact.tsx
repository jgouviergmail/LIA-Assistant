'use client';

import Link from 'next/link';
import { ChevronRight, HelpCircle, Settings } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/**
 * Quick access to Help + Settings — a single compact bar above the briefing.
 *
 * These are two SECONDARY destinations sitting right before the day's content.
 * As two large cards (56 px icon badges, decorative orbs, hover lift) they cost
 * ~208 px on a phone and ~104 px on a desktop to say "Help" and "Settings" —
 * space taken from the briefing, which is what the page exists for. One bar
 * says the same thing in ~120 px / ~60 px, with nothing removed.
 *
 * Layout is decided by MEASUREMENT, not by taste: "Einstellungen" is 92 px at
 * 14 px/600 in Inter, and two side-by-side segments leave 54-78 px of text
 * width at 320 px — German would be truncated. So the segments stack below
 * `sm` (two full-width rows, everything legible in all six locales) and sit
 * side by side above it, as one horizontal bar.
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
