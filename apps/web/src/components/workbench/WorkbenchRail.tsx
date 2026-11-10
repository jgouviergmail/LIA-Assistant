'use client';

/**
 * WorkbenchRail — the « Tools » section's navigation (ADR-369).
 *
 * A horizontal row of pills above the open tool, at every width, so the tool
 * keeps the whole width (a vertical rail spent a quarter of a laptop screen)
 * and a phone switches tools in one gesture instead of going back to a list.
 * A named landmark of LINKS (each tool has its own page), the open one stated
 * with `aria-current` and brought into view when the row scrolls. Two groups
 * (D6): « Tools » holds the usable tools and the ones whose provider must be
 * reconnected (marked, still linked to their page, which says what to do);
 * « To connect » follows, quieter, pointing at Settings › Connectors. A tool the
 * instance offers no provider for is in neither. The open pill is the page's
 * title, so it says whose service the tool works on. Below `lg` the row scrolls
 * and every pill takes a finger's height. The mail's pill says what the inbox
 * leaves unread, on every tool's page.
 */
import Link from 'next/link';
import { PlugZap, TriangleAlert } from '@/lib/icons';
import { useEffect, useId, useRef, type ReactNode, type Ref } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { settingsSectionHref } from '@/lib/settings-sections';
import { cn } from '@/lib/utils';
import { providerVendor, railGroups, toolPath, toolSpec } from '@/lib/workbench/tools';
import type {
  WorkbenchAvailability,
  WorkbenchToolAvailability,
  WorkbenchToolId,
} from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

export interface WorkbenchRailProps {
  lng: Language;
  availability: WorkbenchAvailability;
  /** The tool whose page is open; null on the section's root. */
  activeTool: WorkbenchToolId | null;
  /** What the inbox leaves unread, once read. */
  mailUnread?: number;
}

/** Past this, the pill says « more » rather than widen. */
const UNREAD_BADGE_MAX = 99;

export function WorkbenchRail({ lng, availability, activeTool, mailUnread }: WorkbenchRailProps) {
  const { t } = useTranslation(lng);
  const groups = railGroups(availability);
  const connectorsHref = settingsSectionHref(lng, 'connectors');
  const openRef = useRef<HTMLAnchorElement>(null);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    // `nearest` on both axes: the row scrolls to the open pill, the page never.
    const bring = () => openRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    bring();
    // The tool's actions come to share the row after this first look.
    const row = navRef.current;
    if (!row || typeof ResizeObserver === 'undefined') return;
    const watch = new ResizeObserver(bring);
    watch.observe(row);
    return () => watch.disconnect();
  }, [activeTool]);

  // `relative`: the screen-reader notes are absolutely positioned; without a
  // positioned scroll container they escape its clip and widen the page
  // (measured: a 712 px document on a 390 px phone). `scroll-px-4`: the open
  // pill is brought into view inside the page's gutter, never flush against
  // the screen's edge (measured: 99.6 % of it visible at 320 px without).
  return (
    <nav
      ref={navRef}
      aria-label={t('workbench.rail.label')}
      className="relative min-w-0 flex-1 basis-full scroll-px-4 xl:basis-48 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <div className="flex w-max items-center gap-3 py-0.5 sm:w-auto sm:flex-wrap">
        {groups.tools.length > 0 && (
          <RailGroup title={t('workbench.rail.group_tools')} titleHidden>
            {groups.tools.map(item => (
              <RailLink
                key={item.tool}
                item={item}
                href={buildLocalizedPath(toolPath(item.tool), lng)}
                current={item.tool === activeTool}
                linkRef={item.tool === activeTool ? openRef : undefined}
                label={t(toolSpec(item.tool).labelKey)}
                note={
                  item.state === 'reconnect_required' ? (
                    <>
                      <TriangleAlert className="h-3.5 w-3.5 text-warning" aria-hidden="true" />
                      <span className="sr-only">{t('workbench.rail.reconnect')}</span>
                    </>
                  ) : item.tool === 'mail' && mailUnread ? (
                    <UnreadBadge
                      count={mailUnread}
                      label={t('workbench.rail.unread', { count: mailUnread })}
                    />
                  ) : null
                }
              />
            ))}
          </RailGroup>
        )}
        {groups.toConnect.length > 0 && (
          <RailGroup title={t('workbench.rail.group_to_connect')}>
            {groups.toConnect.map(item => (
              <RailLink
                key={item.tool}
                item={item}
                href={connectorsHref}
                current={false}
                quiet
                label={t(toolSpec(item.tool).labelKey)}
                note={<span className="sr-only">{t('workbench.rail.connect')}</span>}
              />
            ))}
          </RailGroup>
        )}
      </div>
    </nav>
  );
}

/** The inbox's unread figure on the mail's pill, past a bound in the fewest characters. */
function UnreadBadge({ count, label }: { count: number; label: string }) {
  return (
    <>
      <span
        aria-hidden="true"
        className="rounded-full bg-primary px-1.5 text-xs font-semibold tabular-nums text-primary-foreground"
      >
        {count > UNREAD_BADGE_MAX ? `${UNREAD_BADGE_MAX}+` : count}
      </span>
      <span className="sr-only">{label}</span>
    </>
  );
}

function RailGroup({
  title,
  titleHidden = false,
  children,
}: {
  title: string;
  /** The first group needs no visible title: the pills say what they are. */
  titleHidden?: boolean;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <div className="flex items-center gap-1.5">
      {/* Not a heading: the page's h1 (the tool, or « Tools ») owns the outline;
          the list is named by this label for assistive technology. */}
      <span
        id={titleId}
        className={cn(
          titleHidden
            ? 'sr-only'
            : 'flex shrink-0 items-center gap-1 pl-1 text-xs font-semibold text-muted-foreground'
        )}
      >
        {!titleHidden && <PlugZap className="h-3.5 w-3.5" aria-hidden="true" />}
        {title}
      </span>
      <ul aria-labelledby={titleId} className="flex items-center gap-1.5">
        {children}
      </ul>
    </div>
  );
}

function RailLink({
  item,
  href,
  current,
  quiet = false,
  label,
  note,
  linkRef,
}: {
  item: WorkbenchToolAvailability;
  href: string;
  current: boolean;
  /** A tool to connect: drawn quieter than the usable ones. */
  quiet?: boolean;
  label: string;
  note: ReactNode;
  linkRef?: Ref<HTMLAnchorElement>;
}) {
  const { icon: Icon } = toolSpec(item.tool);
  return (
    <li className="shrink-0">
      <Link
        ref={linkRef}
        href={href}
        aria-current={current ? 'page' : undefined}
        className={cn(
          'flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-sm transition-colors lg:min-h-9',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          current && 'border-primary/40 bg-primary/10 font-medium text-primary',
          !current &&
            !quiet &&
            'bg-card text-foreground hover:bg-accent hover:text-accent-foreground',
          quiet &&
            'border-dashed text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )}
      >
        <Icon
          className={cn('h-4 w-4 shrink-0', quiet ? 'text-muted-foreground' : 'text-primary')}
          aria-hidden="true"
        />
        <span>{label}</span>
        {current && item.provider && (
          <span className="hidden text-xs text-muted-foreground sm:inline">
            {providerVendor(item.provider)}
          </span>
        )}
        {note}
      </Link>
    </li>
  );
}
