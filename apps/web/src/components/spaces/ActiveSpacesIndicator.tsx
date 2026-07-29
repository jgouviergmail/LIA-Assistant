'use client';

import { useTranslation } from 'react-i18next';
import { usePathname } from 'next/navigation';
import { Library, Settings2 } from 'lucide-react';
import Link from 'next/link';
import { toast } from 'sonner';

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useSpaces } from '@/hooks/useSpaces';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';
import { fallbackLng } from '@/i18n/settings';

/**
 * Active RAG spaces count in the chat header — a discreet quick-toggle pill
 * (R01), opening per-space switches + a link to the management page.
 *
 * Placement + form (2026-07-29 fix): it rides in the CENTRED middle group of
 * the header (next to the voice badge), which is a normal flex child — NOT the
 * former `absolute left-1/2` row. Equal-weight (`flex-1`) side groups keep the
 * middle visually centred while it SHIFTS by itself, never overlapping, when a
 * side grows (the "processing" / "listening" status pill, the search field).
 * The old absolute centring reserved no width and overlapped the left group;
 * the wider R01 text surfaced that latent collision. Its colour is
 * DELIBERATELY subdued (muted, not the loud primary badge) while its
 * dimensions match the sibling pills exactly (rounded-full, px-3 py-1.5,
 * text-[11px]) — homogeneous in shape, discreet in tone.
 *
 * The accessible name lives on the TRIGGER and is the same at every width
 * (S5b invariant): below `sm` the visible text is the bare count, and a
 * `title` would be hover-only, which touch does not have.
 */
export function ActiveSpacesIndicator() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const lng = pathname ? getLanguageFromPath(pathname) : fallbackLng;
  const { spaces, activeCount, loading, toggleSpace, toggling } = useSpaces();

  // Nothing to toggle: the nav "Knowledge" entry covers discovery (R01).
  if (loading || spaces.length === 0) return null;

  const handleToggle = async (spaceId: string, spaceName: string) => {
    try {
      const result = await toggleSpace(spaceId);
      if (result) {
        toast.success(
          result.is_active
            ? t('spaces.toggle_activated', { name: spaceName })
            : t('spaces.toggle_deactivated', { name: spaceName })
        );
      }
    } catch {
      // Unlike the spaces page, the reverted switch may be OFF-SCREEN here
      // (menu closed on outside tap) — say the failure out loud.
      toast.error(t('common.error'));
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('spaces.indicator_tooltip', { count: activeCount })}
          // Homogeneous with the sibling header pills (offline / processing /
          // delete / context): same rounded-full px-3 py-1.5 text-[11px]
          // shell. Discreet TONE: muted neutral, not the primary badge.
          className="flex shrink-0 items-center gap-1.5 rounded-full border border-border/60 bg-muted/50 px-3 py-1.5 text-[11px] mobile:text-xs font-semibold text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Library className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">{t('spaces.indicator', { count: activeCount })}</span>
          <span className="sm:hidden tabular-nums">{activeCount}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel>{t('spaces.title')}</DropdownMenuLabel>
        {spaces.map(space => (
          <DropdownMenuCheckboxItem
            key={space.id}
            checked={space.is_active}
            disabled={toggling}
            // preventDefault keeps the menu open: toggling several spaces in
            // a row must not cost one open gesture per space.
            onSelect={event => event.preventDefault()}
            onCheckedChange={() => void handleToggle(space.id, space.name)}
          >
            <span className="truncate">{space.name}</span>
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link
            href={buildLocalizedPath('/dashboard/spaces', lng)}
            className="w-full cursor-pointer"
          >
            <Settings2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            {t('spaces.quick_manage')}
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
