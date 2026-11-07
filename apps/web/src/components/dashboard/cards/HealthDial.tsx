/**
 * HealthDial — one measure of the day on its dial (owner, 2026-11-06).
 *
 * The band today stands in is lit, a mark says where in it, and a notch where the average of
 * the window falls. A picture of the figures printed around it, so it is hidden from the ear;
 * a day nothing was read draws no mark and lights nothing, it is never drawn as a zero. What the
 * dial holds in its middle is the card's.
 */
import type { ReactNode } from 'react';

import {
  bandArc,
  bandOf,
  dialPosition,
  HEALTH_BANDS,
  HEALTH_SCALES,
  type HealthTone,
} from '@/lib/health-dial';
import { cn } from '@/lib/utils';
import type { HealthKind } from '@/types/briefing';

/** What a tone reads as on a figure. */
export const HEALTH_TONE_INK: Readonly<Record<HealthTone, string>> = {
  red: 'text-red-700 dark:text-red-300',
  orange: 'text-orange-700 dark:text-orange-300',
  green: 'text-green-700 dark:text-green-300',
};

/**
 * What a tone reads as on the dial, where two bands touch: the figures' red and orange are
 * one colour side by side (measured ΔE 5.4 against a floor of 15; here 23.8). The band is also
 * told by the mark on it and the figure, so a colour is never all it has.
 */
const BAND_INK: Readonly<Record<HealthTone, string>> = {
  red: 'text-red-600 dark:text-red-400',
  orange: 'text-amber-500 dark:text-amber-400',
  green: 'text-green-600 dark:text-green-400',
};

const CENTRE = 60;
const RADIUS = 48;
const STROKE = 8;
/** The dial opens at the bottom: from a quarter past the left, three quarters of a turn. */
const START_DEGREES = 135;
const SWEEP_DEGREES = 270;
/** Where the notch of the average stands, outside the arc. */
const NOTCH_FROM = RADIUS + 7;
const NOTCH_TO = RADIUS + 11;

function pointAt(position: number, radius: number): { x: number; y: number } {
  const angle = ((START_DEGREES + SWEEP_DEGREES * position) * Math.PI) / 180;
  const round = (value: number) => Math.round(value * 100) / 100;
  return {
    x: round(CENTRE + radius * Math.cos(angle)),
    y: round(CENTRE + radius * Math.sin(angle)),
  };
}

function arcOf(from: number, to: number): string {
  const start = pointAt(from, RADIUS);
  const end = pointAt(to, RADIUS);
  return `M${start.x} ${start.y}A${RADIUS} ${RADIUS} 0 0 1 ${end.x} ${end.y}`;
}

export interface HealthDialProps {
  kind: HealthKind;
  /** Today's rounded value; null when nothing was read. */
  today: number | null;
  /** The window's rounded average; null when the window is empty. */
  average: number | null;
  /** What stands in its middle. */
  children: ReactNode;
}

export function HealthDial({ kind, today, average, children }: HealthDialProps) {
  const scale = HEALTH_SCALES[kind];
  const band = today === null ? null : bandOf(scale, today);
  const mark = today === null ? null : pointAt(dialPosition(scale, today), RADIUS);
  const position = average === null ? null : dialPosition(scale, average);
  const notchFrom = position === null ? null : pointAt(position, NOTCH_FROM);
  const notchTo = position === null ? null : pointAt(position, NOTCH_TO);
  return (
    <div className="@container relative w-full max-w-44">
      <svg
        viewBox="0 0 120 104"
        className="block h-auto w-full"
        aria-hidden="true"
        focusable="false"
        data-testid="health-dial"
      >
        {HEALTH_BANDS.map(index => {
          const { from, to } = bandArc(index);
          return (
            <path
              key={index}
              d={arcOf(from, to)}
              fill="none"
              stroke="currentColor"
              strokeWidth={STROKE}
              strokeLinecap="round"
              data-band={index}
              data-lit={index === band}
              className={cn(BAND_INK[scale.tones[index]], index !== band && 'opacity-25')}
            />
          );
        })}
        {notchFrom && notchTo && (
          <line
            x1={notchFrom.x}
            y1={notchFrom.y}
            x2={notchTo.x}
            y2={notchTo.y}
            strokeWidth="2.5"
            strokeLinecap="round"
            className="stroke-foreground/70"
            data-testid="health-dial-average"
          />
        )}
        {mark && band !== null && (
          <circle
            cx={mark.x}
            cy={mark.y}
            r="7"
            fill="currentColor"
            strokeWidth="2.5"
            className={cn(BAND_INK[scale.tones[band]], 'stroke-card')}
            data-testid="health-dial-today"
          />
        )}
      </svg>
      {/* A square on the circle's centre: the box of the drawing stops above it. */}
      <div className="absolute inset-x-0 top-0 flex aspect-square flex-col items-center justify-center gap-0.5">
        {children}
      </div>
    </div>
  );
}
