/**
 * Glass surface of the cosmos identity: translucent background, 1px luminous
 * border, colored shadow — with an optional slight tilt that straightens on
 * hover (the mockup-validated "leaning card" device). Server-safe: pure
 * classes, no client behavior.
 */

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

const TILT_CLASSES = {
  '-2': 'cosmos-tilt-n2',
  '-1': 'cosmos-tilt-n1',
  '1': 'cosmos-tilt-1',
  '2': 'cosmos-tilt-2',
} as const;

export type GlowCardTilt = -2 | -1 | 1 | 2;

interface GlowCardProps {
  children: ReactNode;
  /** Degrees of resting rotation; omit for a straight card. */
  tilt?: GlowCardTilt;
  className?: string;
}

export function GlowCard({ children, tilt, className }: GlowCardProps) {
  const tiltClass = tilt === undefined ? undefined : TILT_CLASSES[`${tilt}`];
  return <div className={cn('cosmos-glass', tiltClass, className)}>{children}</div>;
}
