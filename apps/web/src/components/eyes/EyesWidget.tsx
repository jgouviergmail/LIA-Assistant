'use client';

/**
 * EyesWidget — the floating shell around the selected companion renderer.
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
import { useAvatarRuntime } from '@/lib/avatars/runtime';
import { cn } from '@/lib/utils';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { EyesFace, type EyesFaceProps } from '@/components/eyes/EyesFace';
import { useLiaGender } from '@/hooks/useLiaGender';
import {
  useEyesBehavior,
  type EyesBehaviorProps,
  type EyesBehavior,
} from '@/components/eyes/useEyesBehavior';
import { useEyesAnchor, type AnchorPosition } from '@/components/eyes/useEyesAnchor';
import { useEyesDrag, type EyesDrag } from '@/components/eyes/useEyesDrag';
import { useEyesParallax } from '@/components/eyes/useEyesParallax';
import { useCompanionEnvironment } from './useCompanionEnvironment';
import { useEyesAvoidance } from './useEyesAvoidance';
import {
  useEyesWidgetStore,
  type EyesSurface,
  type EyesSize,
  type EyesSizeSetting,
  type EyesPosition,
} from '@/stores/eyesWidgetStore';
import type { Gaze } from '@/components/eyes/expression-engine';
import type { EyeStyleId } from '@/components/eyes/eye-styles';
import type { SpiritVariant } from '@/components/spirit/catalogue';

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

/** Fallback corner per surface: above the composer on the chat (the dock
 * measures the header; this is what shows before it has); the bottom-right
 * corner on the landing, which has no dock at all. */
const FALLBACK_ANCHOR_CLASSES: Record<EyesSurface, string> = {
  chat: 'bottom-32 right-6',
  landing: 'bottom-6 right-6',
};

/** 'auto' stays small on the public landing; the chat scales with the viewport. */
function resolveEyesSize(
  setting: EyesSizeSetting,
  isDesktop: boolean,
  surface: EyesSurface
): EyesSize {
  if (setting !== 'auto') return setting;
  return surface === 'chat' && isDesktop ? 'lg' : 'sm';
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

/** Dock and fallback avoidance share the same ownership of default placement. */
function useWidgetPlacement(
  root: React.RefObject<HTMLDivElement | null>,
  active: boolean,
  surface: EyesSurface,
  dockToChat: boolean | undefined,
  position: EyesPosition | null,
  drag: EyesDrag
): { placement: React.CSSProperties | undefined; style: React.CSSProperties } {
  const defaultPosition = active && surface === 'chat' && !position && !drag.dragPos;
  const anchor = useEyesAnchor(root, defaultPosition && dockToChat !== false);
  const avoidance = useEyesAvoidance(root, defaultPosition && !anchor);
  const placement = widgetStyle(drag.displayPos, position, anchor ?? avoidance.position);
  return {
    placement,
    style: { ...placement, pointerEvents: avoidance.blocked ? 'none' : undefined },
  };
}

/** Being carried startles: wide eyes while dragging, everything else paused. */
function eyesDisplayProps(
  dragging: boolean,
  behavior: EyesBehavior,
  resolved: { gaze: Gaze | null; ms: number | undefined },
  size: EyesSize,
  styleId: EyeStyleId
): Omit<EyesFaceProps, 'variant'> {
  if (dragging) {
    return {
      expression: 'surprise',
      gaze: null,
      size,
      styleId,
      idleFamily: behavior.family,
      blinking: behavior.blinking,
      blinkMask: behavior.blinkMask,
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
    blinkMask: behavior.blinkMask,
    gesture: behavior.gesture,
    emote: behavior.emote?.glyph ?? null,
    emoteLeaving: behavior.emote?.leaving ?? false,
    accessory: behavior.accessory,
    emphasis: behavior.emphasis,
    responseWeight: behavior.responseWeight,
  };
}

/** Hover/focus/tap-revealed toolbar — inert while invisible. */
function EyesToolbar(props: {
  tapVisible: boolean;
  cycleLabel: string;
  sizeLabel: string;
  hideLabel: string;
  onCycleSize?: () => void;
  onHide: () => void;
}) {
  const buttonClasses =
    'flex h-6 w-6 max-sm:h-11 max-sm:w-11 items-center justify-center rounded-full bg-muted text-muted-foreground shadow ring-1 ring-border transition-colors hover:text-foreground';
  return (
    <div
      className={cn(
        'lia-eyes-toolbar absolute -top-3 left-1/2 flex -translate-x-1/2 items-center gap-1 transition-opacity',
        'group-hover:pointer-events-auto group-hover:opacity-100',
        'group-focus-within:pointer-events-auto group-focus-within:opacity-100',
        props.tapVisible ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
      )}
    >
      {props.onCycleSize && (
        <button
          type="button"
          onClick={props.onCycleSize}
          aria-label={props.cycleLabel}
          title={props.sizeLabel}
          className={buttonClasses}
        >
          <Scaling className="h-3.5 w-3.5" />
        </button>
      )}
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

/**
 * Minimized state: a 12 px dot on a 44 px target — in the surface's corner,
 * or wherever the eyes were last dragged, and draggable itself (owner,
 * 2026-09-10): a dot parked over what somebody is reading must move too.
 * It shares the widget's persisted spot, so the eyes come back where the
 * dot was left. A press that travels is a drag; the click that follows a
 * drop is swallowed rather than read as « show ».
 */
function EyesRestoreDot(props: { label: string; onShow: () => void; surface: EyesSurface }) {
  const ref = useRef<HTMLButtonElement>(null);
  const position = useEyesWidgetStore(s =>
    props.surface === 'landing' ? s.landingPosition : s.position
  );
  const drag = useEyesDrag(ref, props.surface);
  return (
    <button
      ref={ref}
      type="button"
      onClick={() => {
        if (drag.wasRecentDrag()) return;
        props.onShow();
      }}
      onPointerDown={drag.onPointerDown}
      onPointerMove={drag.onPointerMove}
      onPointerUp={drag.onPointerUp}
      onPointerCancel={drag.onPointerUp}
      onKeyDown={drag.onKeyDown}
      aria-label={props.label}
      style={widgetStyle(drag.displayPos, position, null)}
      className={cn(
        'group fixed z-30 flex h-11 w-11 cursor-grab touch-none items-end justify-end active:cursor-grabbing',
        !drag.dragPos && !position && FALLBACK_ANCHOR_CLASSES[props.surface]
      )}
    >
      <span className="h-3 w-3 rounded-full bg-primary/60 shadow-md ring-2 ring-background transition-colors group-hover:bg-primary" />
    </button>
  );
}

export type EyesWidgetProps = EyesBehaviorProps & {
  /** Where the widget lives — the chat (default) or the public landing.
   * Decides the persisted position slot, the dock and the fallback corner;
   * the face, its life and its preferences are the same everywhere. */
  surface?: EyesSurface;
  /** Presentation overrides never overwrite application preferences. */
  styleId?: EyeStyleId;
  size?: EyesSize;
  variant?: SpiritVariant;
  /** Pages without chat landmarks use the corner directly, so navigation
   * never briefly reuses a stale header position. */
  dockToChat?: boolean;
};

function widgetPresentation(
  props: Pick<EyesWidgetProps, 'styleId' | 'size' | 'variant'>,
  preference: {
    styleId: EyeStyleId;
    size: EyesSizeSetting;
    variant: SpiritVariant;
    cycleSize: () => void;
  },
  viewport: { isDesktop: boolean; surface: EyesSurface }
) {
  return {
    styleId: props.styleId ?? preference.styleId,
    size: props.size ?? resolveEyesSize(preference.size, viewport.isDesktop, viewport.surface),
    variant: props.variant ?? preference.variant,
    cycleSize: props.size ? undefined : preference.cycleSize,
  };
}

/**
 * Memoized on purpose: the chat page re-renders on every streamed token
 * batch, while the widget's three scalar props only change on phase
 * transitions — memo turns those token flushes into no-ops here.
 */
function useWidgetPresence(visible: boolean, surface: EyesSurface) {
  const hiddenByAvatar = useAvatarRuntime().present && surface === 'chat';
  const mounted = useSyncExternalStore(
    hydrationSubscribe,
    () => true,
    () => false
  );
  const enabled = visible && !hiddenByAvatar;
  const active = mounted && enabled;
  useCompanionEnvironment(surface === 'chat' && active);
  return { mounted, hiddenByAvatar, enabled, active };
}

export const EyesWidget = memo(function EyesWidget(props: EyesWidgetProps) {
  const { t } = useTranslation();
  const { isMale } = useLiaGender();
  const surface = props.surface ?? 'chat';
  const { visible, size, style: preferredStyle, setVisible, cycleSize } = useEyesWidgetStore();
  const { mounted, hiddenByAvatar, enabled, active } = useWidgetPresence(visible, surface);
  const position = useEyesWidgetStore(s =>
    surface === 'landing' ? s.landingPosition : s.position
  );
  // A minimized widget keeps its hook mounted (Rules of Hooks) but the whole
  // live machinery off — the restore dot must cost nothing.
  const behavior = useEyesBehavior({
    chatStatus: props.chatStatus,
    streamPhase: props.streamPhase,
    hitlAwaiting: props.hitlAwaiting,
    enabled,
  });

  // Client-only gate: the chat page is SSR'd once — defer to avoid any
  // hydration mismatch. useSyncExternalStore (server snapshot false, client
  // snapshot true) instead of a mount effect: no setState-in-effect (ratchet).

  const rootRef = useRef<HTMLDivElement>(null);
  const drag = useEyesDrag(rootRef, surface, active);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const presentation = widgetPresentation(
    props,
    { styleId: preferredStyle, size, variant: isMale ? 'male' : 'female', cycleSize },
    { isDesktop, surface }
  );

  // Default docked spot: centered between the header's left cluster and the
  // delete button. Only measured while no custom position is stored — and
  // only on the chat: the landing has no dock, its default is a corner.
  const { placement, style: placementStyle } = useWidgetPlacement(
    rootRef,
    active,
    surface,
    props.dockToChat,
    position,
    drag
  );

  // Desktop cursor parallax — gated, expiring (see useEyesParallax).
  const gazeFree =
    behavior.frame.gaze === null && PARALLAX_EXPRESSIONS.has(behavior.frame.expression);
  const parallax = useEyesParallax(rootRef, active && gazeFree);

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

  if (!mounted || hiddenByAvatar) return null;

  if (!visible) {
    return (
      <EyesRestoreDot label={t('eyes.restore')} onShow={() => setVisible(true)} surface={surface} />
    );
  }

  const resolved = resolveGaze(behavior, gazeFree ? parallax : null);
  // The positioning resolver is also the authority on whether a fallback is
  // needed; duplicating its three cases in the JSX can disagree with it.

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
      style={placementStyle}
      className={cn(
        'lia-eyes-widget group fixed z-30 select-none touch-none rounded-2xl p-1.5',
        'cursor-grab active:cursor-grabbing',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60',
        // No stored position and the composer anchor not measured yet →
        // CSS fallback corner above the input area.
        !placement && FALLBACK_ANCHOR_CLASSES[surface]
      )}
    >
      <EyesFace
        {...eyesDisplayProps(
          drag.dragPos !== null,
          behavior,
          resolved,
          presentation.size,
          presentation.styleId
        )}
        variant={presentation.variant}
      />
      <EyesToolbar
        tapVisible={toolbarTapVisible}
        cycleLabel={t('eyes.cycle_size')}
        sizeLabel={t(`eyes.sizes.${presentation.size}`)}
        hideLabel={t('eyes.minimize')}
        onCycleSize={presentation.cycleSize}
        onHide={() => setVisible(false)}
      />
    </div>
  );
});
