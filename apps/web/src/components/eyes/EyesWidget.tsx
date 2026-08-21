'use client';

/**
 * EyesWidget — the floating shell around ExpressiveEyes on the chat page.
 *
 * Interaction contract:
 *  - drag anywhere with a pointer, arrow keys move it (useEyesDrag owns the
 *    whole geometry state machine and its persistence)
 *  - toolbar: hover/focus reveals it on desktop, a TAP summons it on touch
 *    (auto-hides); hidden = inert (never invisible-yet-clickable)
 *  - hidden widget → a small restore dot near the composer (never fully
 *    gone — same doctrine as CompanionPresence)
 *  - default dock: horizontally centered ABOVE the composer's send button
 *    (useEyesAnchor), with animation clearance; size 'auto' resolves small
 *    on phones, large on desktop
 *  - desktop-only cursor parallax with expiry (useEyesParallax)
 *
 * z-30: below dialogs/toasts/selection (z-50) and the search bar (z-40) —
 * and the whole widget is user-movable anyway.
 */

import { memo, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Scaling, X } from 'lucide-react';

import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { ExpressiveEyes, type ExpressiveEyesProps } from '@/components/eyes/ExpressiveEyes';
import {
  useEyesBehavior,
  type EyesBehaviorProps,
  type EyesBehavior,
} from '@/components/eyes/useEyesBehavior';
import { useEyesAnchor, type AnchorPosition } from '@/components/eyes/useEyesAnchor';
import { useEyesDrag, type EyesDrag } from '@/components/eyes/useEyesDrag';
import { useEyesParallax } from '@/components/eyes/useEyesParallax';
import {
  useEyesWidgetStore,
  type EyesSize,
  type EyesSizeSetting,
  type EyesPosition,
} from '@/stores/eyesWidgetStore';
import type { Gaze } from '@/components/eyes/expression-engine';
import type { EyeStyleId } from '@/components/eyes/eye-styles';

/** Expressions whose gaze the cursor parallax may borrow. */
const PARALLAX_EXPRESSIONS: ReadonlySet<string> = new Set([
  'neutral',
  'attentive',
  'joy',
  'tender',
  'bored',
  'speaking',
]);

/** Inert subscription for the hydration useSyncExternalStore gate. */
const hydrationSubscribe = () => () => {};

/** On touch screens the tap-summoned toolbar hides itself after this long. */
const TOOLBAR_TAP_HIDE_MS = 4000;

/** Fallback corner when the composer anchor is not in the DOM. */
const FALLBACK_ANCHOR_CLASSES = 'bottom-32 right-6';

/** 'auto' resolves responsively: discreet on phones, present on desktop. */
function resolveEyesSize(setting: EyesSizeSetting, isDesktop: boolean): EyesSize {
  if (setting !== 'auto') return setting;
  return isDesktop ? 'lg' : 'sm';
}

/** Gaze priority: engine-directed > live cursor parallax > idle wander.
 * Only the wander carries its own travel time (saccade jump / eased return). */
function resolveGaze(
  behavior: EyesBehavior,
  parallax: Gaze | null
): { gaze: Gaze | null; ms: number | undefined } {
  if (behavior.frame.gaze) return { gaze: behavior.frame.gaze, ms: undefined };
  if (parallax) return { gaze: parallax, ms: undefined };
  if (behavior.idleGaze) return { gaze: behavior.idleGaze.gaze, ms: behavior.idleGaze.ms };
  return { gaze: null, ms: undefined };
}

/** Inline position: px while dragging, stored viewport %, measured dock. */
function widgetStyle(
  dragPos: EyesDrag['dragPos'],
  position: EyesPosition | null,
  anchorPos: AnchorPosition | null
): React.CSSProperties | undefined {
  if (dragPos) return { left: dragPos.x, top: dragPos.y };
  if (position) return { left: `${position.xPct}%`, top: `${position.yPct}%` };
  return anchorPos ?? undefined;
}

/** Being carried startles: wide eyes while dragging, everything else paused. */
function eyesDisplayProps(
  dragging: boolean,
  behavior: EyesBehavior,
  resolved: { gaze: Gaze | null; ms: number | undefined },
  size: EyesSize,
  styleId: EyeStyleId
): ExpressiveEyesProps {
  if (dragging) {
    return {
      expression: 'surprise',
      gaze: null,
      size,
      styleId,
      idleFamily: behavior.family,
      blinking: behavior.blinking,
    };
  }
  return {
    expression: behavior.frame.expression,
    gaze: resolved.gaze,
    gazeDurationMs: resolved.ms,
    size,
    styleId,
    idleFamily: behavior.family,
    blinking: behavior.blinking,
    gesture: behavior.gesture,
    emote: behavior.emote?.glyph ?? null,
    emoteLeaving: behavior.emote?.leaving ?? false,
  };
}

/** Hover/focus/tap-revealed toolbar — inert while invisible. */
function EyesToolbar(props: {
  tapVisible: boolean;
  cycleLabel: string;
  hideLabel: string;
  onCycleSize: () => void;
  onHide: () => void;
}) {
  const buttonClasses =
    'flex h-6 w-6 items-center justify-center rounded-full bg-muted text-muted-foreground shadow ring-1 ring-border transition-colors hover:text-foreground [@media(hover:none)]:h-8 [@media(hover:none)]:w-8';
  return (
    <div
      className={cn(
        'absolute -top-3 left-1/2 flex -translate-x-1/2 items-center gap-1 transition-opacity',
        'group-hover:pointer-events-auto group-hover:opacity-100',
        'group-focus-within:pointer-events-auto group-focus-within:opacity-100',
        props.tapVisible ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
      )}
    >
      <button
        type="button"
        onClick={props.onCycleSize}
        aria-label={props.cycleLabel}
        className={buttonClasses}
      >
        <Scaling className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={props.onHide}
        aria-label={props.hideLabel}
        className={buttonClasses}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/** Minimized state: a 12 px dot on a 44 px target near the composer. */
function EyesRestoreDot(props: { label: string; onShow: () => void }) {
  return (
    <button
      type="button"
      onClick={props.onShow}
      aria-label={props.label}
      className={cn(
        'group fixed z-30 flex h-11 w-11 items-end justify-end',
        FALLBACK_ANCHOR_CLASSES
      )}
    >
      <span className="h-3 w-3 rounded-full bg-primary/60 shadow-md ring-2 ring-background transition-colors group-hover:bg-primary" />
    </button>
  );
}

export type EyesWidgetProps = EyesBehaviorProps;

/**
 * Memoized on purpose: the chat page re-renders on every streamed token
 * batch, while the widget's three scalar props only change on phase
 * transitions — memo turns those token flushes into no-ops here.
 */
export const EyesWidget = memo(function EyesWidget(props: EyesWidgetProps) {
  const { t } = useTranslation();
  const { visible, size, style: eyeStyle, position, setVisible, cycleSize } = useEyesWidgetStore();
  // A minimized widget keeps its hook mounted (Rules of Hooks) but the whole
  // live machinery off — the restore dot must cost nothing.
  const behavior = useEyesBehavior({ ...props, enabled: visible });

  // Client-only gate: the chat page is SSR'd once — defer to avoid any
  // hydration mismatch. useSyncExternalStore (server snapshot false, client
  // snapshot true) instead of a mount effect: no setState-in-effect (ratchet).
  const mounted = useSyncExternalStore(
    hydrationSubscribe,
    () => true,
    () => false
  );

  const rootRef = useRef<HTMLDivElement>(null);
  const drag = useEyesDrag(rootRef);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const resolvedSize = resolveEyesSize(size, isDesktop);

  // Default docked spot: centered between the header's left cluster and the
  // delete button. Only measured while no custom position is stored.
  const anchorEnabled = visible && !position && !drag.dragPos;
  const anchorPos = useEyesAnchor(rootRef, anchorEnabled);

  // Desktop cursor parallax — gated, expiring (see useEyesParallax).
  const gazeFree =
    behavior.frame.gaze === null && PARALLAX_EXPRESSIONS.has(behavior.frame.expression);
  const parallax = useEyesParallax(rootRef, mounted && visible && gazeFree);

  // Two quick drags can still satisfy the browser's dblclick heuristics —
  // a wink right after dropping the widget reads as a glitch, not a wink.
  const onDoubleClick = () => {
    if (drag.wasRecentDrag()) return;
    behavior.wink();
  };

  // Touch screens have no hover: a TAP on the eyes summons the toolbar (and
  // a second tap — or the timer below — dismisses it). A permanently visible
  // toolbar was ruining the animation on mobile (owner feedback 2026-08-20).
  const [toolbarTapVisible, setToolbarTapVisible] = useState(false);
  const onSurfaceClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button')) return;
    if (!window.matchMedia('(hover: none)').matches) return;
    if (drag.wasRecentDrag()) return;
    setToolbarTapVisible(v => !v);
  };
  useEffect(() => {
    if (!toolbarTapVisible) return;
    const id = setTimeout(() => setToolbarTapVisible(false), TOOLBAR_TAP_HIDE_MS);
    return () => clearTimeout(id);
  }, [toolbarTapVisible]);

  if (!mounted) return null;

  if (!visible) {
    return <EyesRestoreDot label={t('eyes.restore')} onShow={() => setVisible(true)} />;
  }

  const resolved = resolveGaze(behavior, gazeFree ? parallax : null);

  return (
    <div
      ref={rootRef}
      role="group"
      aria-label={t('eyes.widget_label')}
      tabIndex={0}
      onPointerDown={drag.onPointerDown}
      onPointerMove={drag.onPointerMove}
      onPointerUp={drag.onPointerUp}
      onPointerCancel={drag.onPointerUp}
      onKeyDown={drag.onKeyDown}
      onClick={onSurfaceClick}
      onDoubleClick={onDoubleClick}
      style={widgetStyle(drag.dragPos, position, anchorPos)}
      className={cn(
        'lia-eyes-widget group fixed z-30 select-none touch-none rounded-2xl p-1.5',
        'cursor-grab active:cursor-grabbing',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60',
        // No stored position and the composer anchor not measured yet →
        // CSS fallback corner above the input area.
        !drag.dragPos && !position && !anchorPos && FALLBACK_ANCHOR_CLASSES
      )}
    >
      <ExpressiveEyes
        {...eyesDisplayProps(drag.dragPos !== null, behavior, resolved, resolvedSize, eyeStyle)}
      />
      <EyesToolbar
        tapVisible={toolbarTapVisible}
        cycleLabel={t('eyes.cycle_size')}
        hideLabel={t('eyes.minimize')}
        onCycleSize={cycleSize}
        onHide={() => setVisible(false)}
      />
    </div>
  );
});
