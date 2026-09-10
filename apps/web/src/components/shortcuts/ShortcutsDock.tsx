'use client';

/**
 * ShortcutsDock — the floating menu of the settings sections a person pinned
 * (ADR-277), on every dashboard screen.
 *
 * What it is: a glass capsule at the right edge, mid-height, one 44 px link
 * per pinned section — the section's own icon in its group's tone, its title
 * on hover, focus and for a screen reader — that navigates to the section.
 * What it does: it moves (pointer drag, arrow keys on the capsule itself) and
 * it folds into a restore button that moves the same way (owner, 2026-09-10);
 * it never resizes. The fold button sits ABOVE the first shortcut, where a
 * thumb reaching for the top of the capsule finds it. The geometry is the eyes
 * widget's (`useFloatingDrag`), the folded state and the spot are persisted
 * per device, WHAT is pinned comes from the account (`useAuth().user`) — no
 * request of its own, so a page costs nothing more for carrying it.
 *
 * It renders nothing without a pinned section, and it drops what this
 * account cannot open: an administration token pinned by a superuser who no
 * longer is one would be a link to an absent pane. The other gates are the
 * pane's own to say.
 *
 * z-30: below dialogs/toasts/selection (z-50) and the search bar (z-40) —
 * and the whole capsule is user-movable anyway.
 */

import { useCallback, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { ChevronsDownUp, GripHorizontal, Pin } from 'lucide-react';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from '@/hooks/useAuth';
import {
  useFloatingDrag,
  type FloatingPosition,
  type PixelPosition,
} from '@/hooks/useFloatingDrag';
import { knownShortcutTokens } from '@/hooks/useSettingsShortcuts';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { toneForSection } from '@/lib/settings-group-tones';
import { SETTINGS_SEARCH_META } from '@/lib/settings-search';
import { SETTINGS_SECTION_ICONS } from '@/lib/settings-section-icons';
import {
  SETTINGS_SECTIONS,
  settingsSectionHref,
  type SettingsSectionToken,
} from '@/lib/settings-sections';
import { cn } from '@/lib/utils';
import { useShortcutsDockStore } from '@/stores/shortcutsDockStore';

/** Inert subscription for the hydration useSyncExternalStore gate. */
const hydrationSubscribe = () => () => {};

/** The default spot: the right edge, mid-height, clear of the eyes (above
 * the composer, bottom-right) and of the companion (bottom-left). */
const DEFAULT_SPOT_CLASSES = 'right-3 top-1/2 -translate-y-1/2';

/** The folded button's side: the capsule unfolds from the button's edge. */
const FOLDED_PX = 44;

/**
 * Inline position: px while dragging, stored viewport %, else the default spot.
 *
 * Unfolded from the lower half of the screen the capsule grows UPWARD: its
 * foot is pinned where the folded button's foot was (a `bottom`, so no height
 * needs measuring) and the stored spot stays the button's, so folding again
 * puts the button back where it was. From the upper half it grows downward
 * from the same top (owner, 2026-09-10: it butted the bottom of the screen).
 */
function dockStyle(
  dragPos: PixelPosition | null,
  position: FloatingPosition | null,
  growUp = false
): React.CSSProperties | undefined {
  if (dragPos) return { left: dragPos.x, top: dragPos.y };
  if (position && growUp) {
    return {
      left: `${position.xPct}%`,
      bottom: `calc(100% - ${position.yPct}% - ${FOLDED_PX}px)`,
    };
  }
  if (position) return { left: `${position.xPct}%`, top: `${position.yPct}%` };
  return undefined;
}

/** Whether a spot is in the lower half of the screen — where a capsule grows up. */
export function unfoldsUpward(position: FloatingPosition | null): boolean {
  return position !== null && position.yPct > 50;
}

const GLASS =
  'fixed z-30 rounded-full border border-border/60 bg-background/85 shadow-lg backdrop-blur-xl';

export interface ShortcutsDockProps {
  lng: Language;
}

export function ShortcutsDock({ lng }: ShortcutsDockProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { position, minimized, setPosition, setMinimized } = useShortcutsDockStore();
  // One ref for either surface — the capsule (a `nav`) or the folded button —
  // bound through a callback so the element's type need not be one thing.
  const rootRef = useRef<HTMLElement | null>(null);
  const bindRoot = (element: HTMLElement | null) => {
    rootRef.current = element;
  };
  // Decided when the capsule unfolds, never re-derived: a capsule grown up
  // from the lower half and then DRAGGED commits its real top and grows
  // down from there, so it stays exactly where it was dropped.
  const [growUp, setGrowUp] = useState(false);
  const commitPosition = useCallback(
    (next: FloatingPosition) => {
      setGrowUp(false);
      setPosition(next);
    },
    [setPosition]
  );
  // While it grows up the hook is handed no spot: its keyboard step and its
  // re-clamp then read the capsule's REAL rect instead of a top the capsule
  // is not at.
  const drag = useFloatingDrag(rootRef, growUp ? null : position, commitPosition);

  // Client-only gate: the layout is SSR'd once, and the persisted spot only
  // exists in the browser — render nothing on the server, so nothing can
  // mismatch. useSyncExternalStore rather than a mount effect: no
  // setState-in-effect (ratchet).
  const mounted = useSyncExternalStore(
    hydrationSubscribe,
    () => true,
    () => false
  );

  const tokens = knownShortcutTokens(user?.settings_shortcuts).filter(
    (token: SettingsSectionToken) =>
      SETTINGS_SECTIONS[token].tab !== 'administration' || Boolean(user?.is_superuser)
  );

  if (!mounted || !user || tokens.length === 0) return null;

  if (minimized) {
    return (
      <button
        ref={bindRoot}
        type="button"
        // A press that travels is a drag; the click a drop leaves behind is
        // swallowed rather than read as « unfold ».
        onClick={() => {
          if (drag.wasRecentDrag()) return;
          setGrowUp(unfoldsUpward(position));
          setMinimized(false);
        }}
        onPointerDown={drag.onPointerDown}
        onPointerMove={drag.onPointerMove}
        onPointerUp={drag.onPointerUp}
        onPointerCancel={drag.onPointerUp}
        onKeyDown={drag.onKeyDown}
        aria-label={t('shortcuts_dock.restore')}
        style={dockStyle(drag.dragPos, position)}
        className={cn(
          GLASS,
          'flex h-11 w-11 cursor-grab touch-none items-center justify-center text-primary transition-colors hover:bg-accent/70 active:cursor-grabbing',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          !drag.dragPos && !position && DEFAULT_SPOT_CLASSES
        )}
      >
        <Pin className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
      <nav
        ref={bindRoot}
        aria-label={t('shortcuts_dock.label')}
        tabIndex={0}
        onPointerDown={drag.onPointerDown}
        onPointerMove={drag.onPointerMove}
        onPointerUp={drag.onPointerUp}
        onPointerCancel={drag.onPointerUp}
        onKeyDown={drag.onKeyDown}
        style={dockStyle(drag.dragPos, position, growUp)}
        className={cn(
          GLASS,
          'lia-shortcuts-dock flex select-none touch-none flex-col items-center gap-0.5 p-1',
          'cursor-grab active:cursor-grabbing',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60',
          !drag.dragPos && !position && DEFAULT_SPOT_CLASSES
        )}
      >
        <button
          type="button"
          onClick={() => setMinimized(true)}
          aria-label={t('shortcuts_dock.minimize')}
          className={cn(
            'mb-0.5 flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition-colors',
            'hover:bg-accent/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          )}
        >
          <ChevronsDownUp className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
        <ul className="flex flex-col items-center gap-0.5">
          {tokens.map(token => {
            const Icon = SETTINGS_SECTION_ICONS[token];
            const tone = toneForSection(token);
            const label = t(SETTINGS_SEARCH_META[token].titleKey);
            return (
              <li key={token}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Link
                      href={settingsSectionHref(lng, token)}
                      aria-label={label}
                      className={cn(
                        'flex h-11 w-11 items-center justify-center rounded-full transition-colors hover:bg-accent/70',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                      )}
                    >
                      {/* The tone marks the GROUP, as on the rail: a reader
                          who knows the settings page finds the same map. */}
                      <span
                        className={cn(
                          'flex h-8 w-8 items-center justify-center rounded-full',
                          tone.chip
                        )}
                      >
                        <Icon className={cn('h-4 w-4', tone.glyph)} aria-hidden="true" />
                      </span>
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent side="left">{label}</TooltipContent>
                </Tooltip>
              </li>
            );
          })}
        </ul>
        {/* The grip, at the foot: it says « this moves » to a pointer, and the
            capsule's own name says it to a keyboard reader. */}
        <GripHorizontal className="my-0.5 h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
      </nav>
    </TooltipProvider>
  );
}
