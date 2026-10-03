'use client';

/**
 * The cosmos pages' pause control (WCAG 2.2.2): one button that stops every
 * decorative animation of the page — the nebula, the planet's clouds, the
 * landing's attention canvas — and starts them again.
 *
 * A toggle button: its accessible name stays the same and `aria-pressed`
 * carries the state, the icon showing what a press does (the /more scenes'
 * toggle follows the same convention). The state lives on `<html>`
 * (lib/landing/motion-pause), so every instance — the header row, the
 * mobile menu, the footer — reads one value and a client-side navigation
 * keeps it.
 *
 * Where it sits was measured, not guessed: the landing header's link row is
 * saturated from 880 to 1279 px — an extra 44 px button ran the French row
 * 33 px past an 880 px viewport and 49 px past a 1024 px one (2026-10-03) —
 * so the header carries it from `xl` and in the mobile menu, and every public
 * footer carries it with its label, at every width.
 */

import { useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { Pause, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { isMotionPaused, setMotionPaused, subscribeMotion } from '@/lib/landing/motion-pause';
import { cn } from '@/lib/utils';

/** Before hydration nothing is paused: the server renders the playing state. */
const serverSnapshot = (): boolean => false;

interface MotionToggleProps {
  className?: string;
  /** Shows the name next to the icon (footers); the header keeps the icon alone. */
  withLabel?: boolean;
}

export function MotionToggle({ className, withLabel = false }: MotionToggleProps) {
  const { t } = useTranslation();
  const paused = useSyncExternalStore(subscribeMotion, isMotionPaused, serverSnapshot);
  const Icon = paused ? Play : Pause;

  if (withLabel) {
    return (
      <button
        type="button"
        data-testid="cosmos-motion-toggle"
        onClick={() => setMotionPaused(!paused)}
        aria-pressed={paused}
        className={cn(
          'inline-flex min-h-6 items-center gap-1.5 rounded text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          className
        )}
      >
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {t('landing.motion.pause')}
      </button>
    );
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      data-testid="cosmos-motion-toggle"
      className={cn('w-11 h-11 px-0 max-[380px]:w-9 max-[380px]:h-9', className)}
      onClick={() => setMotionPaused(!paused)}
      aria-pressed={paused}
      aria-label={t('landing.motion.pause')}
      title={t('landing.motion.pause')}
    >
      <Icon className="h-[1.1rem] w-[1.1rem]" aria-hidden="true" />
    </Button>
  );
}
