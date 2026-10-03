/**
 * Page-wide play/pause state for the /more animated scenes.
 *
 * WCAG 2.2.2 (Pause, Stop, Hide): the scenes auto-start and collectively
 * last more than five seconds, so the page must carry an in-page mechanism —
 * prefers-reduced-motion is an OS preference, not a page control. The
 * AnimationPauseToggle is that mechanism; every scene consumes the context
 * through its card and stops scheduling timers while paused.
 *
 * The paused state is the cosmos pages' own (lib/landing/motion-pause): this
 * toggle and the header's pause control are one switch, so pausing either
 * stops the scenes AND the page's background, and the choice is remembered.
 *
 * The default context value keeps `playing: true` so a scene rendered
 * outside the provider (tests, future reuse) animates rather than dying
 * silently.
 */

'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Pause, Play } from 'lucide-react';
import { isMotionPaused, setMotionPaused, subscribeMotion } from '@/lib/landing/motion-pause';

interface MoreAnimationState {
  playing: boolean;
  toggle: () => void;
}

const MoreAnimationContext = createContext<MoreAnimationState>({
  playing: true,
  toggle: () => undefined,
});

export function useMoreAnimation(): MoreAnimationState {
  return useContext(MoreAnimationContext);
}

/** Before hydration nothing is paused: the server renders the scenes playing. */
const serverSnapshot = (): boolean => false;

export function MoreAnimationProvider({ children }: { children: ReactNode }) {
  const paused = useSyncExternalStore(subscribeMotion, isMotionPaused, serverSnapshot);
  const toggle = useCallback(() => setMotionPaused(!isMotionPaused()), []);
  const value = useMemo(() => ({ playing: !paused, toggle }), [paused, toggle]);

  return <MoreAnimationContext.Provider value={value}>{children}</MoreAnimationContext.Provider>;
}

export function AnimationPauseToggle() {
  const { playing, toggle } = useMoreAnimation();
  const { t } = useTranslation();
  const Icon = playing ? Pause : Play;

  return (
    <button
      type="button"
      data-testid="more-pause-toggle"
      onClick={toggle}
      aria-pressed={!playing}
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {t('more.controls.pause_animations')}
    </button>
  );
}
