/**
 * Shared contract between the /more scenes, the scene registry and MoreCard.
 *
 * A scene is a purely decorative animated stage: it receives `active`
 * (in-viewport AND not paused — the WCAG 2.2.2 gate) and its translated
 * micro-labels, pre-resolved by the card so scenes never touch i18n
 * machinery. Continuous CSS animation classes (animate-spin, animate-pulse)
 * must be gated on `active` inside scenes — the timeline freeze alone cannot
 * stop them.
 */

import type { JSX } from 'react';

export interface SceneProps {
  active: boolean;
  labels: Readonly<Record<string, string>>;
}

export type SceneComponent = (props: SceneProps) => JSX.Element;
