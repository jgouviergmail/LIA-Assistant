'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';
import { unobstructedPlacement } from './eyes-placement';
import type { AnchorPosition } from './useEyesAnchor';

interface Placement {
  position: AnchorPosition | null;
  blocked: boolean;
  compact: boolean;
  compactSize: { width: number; height: number } | null;
}
const EMPTY: Placement = { position: null, blocked: false, compact: false, compactSize: null };
const CONTROLS = 'button,a[href],input,select,textarea,summary,[role="button"]';

function occupiedFrame(widget: HTMLElement, body: DOMRect) {
  const toolbar = widget.querySelector('.lia-eyes-toolbar')?.getBoundingClientRect();
  if (!toolbar?.width || !toolbar.height) return body;
  const left = Math.min(body.left, toolbar.left);
  const top = Math.min(body.top, toolbar.top);
  return {
    left,
    top,
    width: Math.max(body.right, toolbar.right) - left,
    height: Math.max(body.bottom, toolbar.bottom) - top,
  };
}

interface ExpandedFrame {
  width: number;
  height: number;
  bodyLeft: number;
  bodyTop: number;
}

function measuredViewport() {
  const viewport = window.visualViewport ?? {
    width: innerWidth,
    height: innerHeight,
    offsetLeft: 0,
    offsetTop: 0,
  };
  const headerBottom =
    document.querySelector('.lia-dashboard-header')?.getBoundingClientRect().bottom ?? 8;
  return {
    width: viewport.width + viewport.offsetLeft,
    minimumLeft: viewport.offsetLeft,
    height: viewport.height + viewport.offsetTop,
    minimumTop: Math.max(viewport.offsetTop, headerBottom),
  };
}

function visibleObstacles(widget: HTMLElement, protectHeadings: boolean) {
  const selector = protectHeadings ? `${CONTROLS},h1,h2,h3,h4,h5,h6` : CONTROLS;
  return [...document.querySelectorAll<HTMLElement>(selector)]
    .filter(control => !widget.contains(control))
    .map(control => control.getBoundingClientRect())
    .filter(box => box.width > 0 && box.height > 0 && box.bottom > 0 && box.top < innerHeight);
}

function compactFrame(widget: HTMLElement) {
  const toolbar = widget.querySelector('.lia-eyes-toolbar')?.getBoundingClientRect();
  return {
    width: Math.max(44, toolbar?.width ?? 0),
    height: Math.max(44, (toolbar?.height ?? 0) + 12),
  };
}

/**
 * When the companion may fold into its compact presence: `fallback` folds it
 * only when the expanded frame finds no free spot, `only` keeps it folded, and
 * `never` keeps the face whole — with no free spot it stays put and lets
 * clicks through (`blocked`), the behaviour a wide screen keeps.
 */
export type CompactPolicy = 'never' | 'fallback' | 'only';

function resolvePlacement(
  preferredBody: AnchorPosition,
  size: ExpandedFrame,
  compactSize: { width: number; height: number },
  bounds: ReturnType<typeof measuredViewport>,
  obstacles: DOMRect[],
  policy: CompactPolicy
): Placement {
  const intended = {
    left: preferredBody.left - size.bodyLeft,
    top: preferredBody.top - size.bodyTop,
  };
  const expanded =
    policy === 'only' ? null : unobstructedPlacement(intended, size, bounds, obstacles);
  if (expanded === null && policy === 'never') {
    return { position: null, blocked: true, compact: false, compactSize: null };
  }
  const compact = expanded === null;
  const safe = expanded ?? unobstructedPlacement(preferredBody, compactSize, bounds, obstacles);
  const offset = compact ? { left: 0, top: 0 } : { left: size.bodyLeft, top: size.bodyTop };
  return {
    position: safe ? { left: safe.left + offset.left, top: safe.top + offset.top } : null,
    blocked: safe === null,
    compact,
    compactSize: compact ? compactSize : null,
  };
}

function samePoint(a: AnchorPosition | null, b: AnchorPosition | null) {
  if (!a || !b) return a === b;
  return a.left === b.left && a.top === b.top;
}
function sameCompactSize(a: Placement['compactSize'], b: Placement['compactSize']) {
  if (!a || !b) return a === b;
  return a.width === b.width && a.height === b.height;
}
function samePlacement(a: Placement, b: Placement) {
  return (
    samePoint(a.position, b.position) &&
    sameCompactSize(a.compactSize, b.compactSize) &&
    a.blocked === b.blocked &&
    a.compact === b.compact
  );
}

function observePlacement(root: RefObject<HTMLElement | null>, schedule: () => void) {
  window.addEventListener('resize', schedule);
  window.visualViewport?.addEventListener('resize', schedule);
  window.visualViewport?.addEventListener('scroll', schedule);
  document.addEventListener('focusin', schedule);
  window.addEventListener('scroll', schedule, true);
  const resize = new ResizeObserver(schedule);
  if (root.current) resize.observe(root.current);
  const mutation = new MutationObserver(schedule);
  mutation.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['aria-expanded', 'open', 'hidden'],
  });
  return () => {
    window.removeEventListener('resize', schedule);
    window.visualViewport?.removeEventListener('resize', schedule);
    window.visualViewport?.removeEventListener('scroll', schedule);
    document.removeEventListener('focusin', schedule);
    window.removeEventListener('scroll', schedule, true);
    resize.disconnect();
    mutation.disconnect();
  };
}

/** Bounded layout observations: no storage write, gesture change or synthetic click. */
export function useEyesAvoidance(
  root: RefObject<HTMLElement | null>,
  enabled: boolean,
  preferred?: AnchorPosition | null,
  options: { compact?: CompactPolicy; protectHeadings?: boolean } = {}
) {
  const compactPolicy = options.compact ?? 'fallback';
  const protectHeadings = options.protectHeadings ?? false;
  const preferredLeft = preferred?.left;
  const preferredTop = preferred?.top;
  const expandedSize = useRef<ExpandedFrame | null>(null);
  const [placement, setPlacement] = useState<Placement>(EMPTY);
  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let frame: number | null = null;
    const measure = () => {
      frame = null;
      const widget = root.current;
      if (!widget) return;
      const rect = widget.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const occupied = occupiedFrame(widget, rect);
      if (widget.dataset.compact !== 'true')
        expandedSize.current = {
          width: occupied.width,
          height: occupied.height,
          bodyLeft: rect.left - occupied.left,
          bodyTop: rect.top - occupied.top,
        };
      const size = expandedSize.current ?? { ...occupied, bodyLeft: 0, bodyTop: 0 };
      const next = resolvePlacement(
        { left: preferredLeft ?? rect.left, top: preferredTop ?? rect.top },
        size,
        compactFrame(widget),
        measuredViewport(),
        visibleObstacles(widget, protectHeadings),
        compactPolicy
      );
      setPlacement(previous => (samePlacement(previous, next) ? previous : next));
    };
    const schedule = () => {
      if (timer !== null || frame !== null) return;
      // Streaming may mutate the DOM every frame. At most one scan per 150 ms.
      timer = setTimeout(() => {
        timer = null;
        frame = requestAnimationFrame(measure);
      }, 150);
    };
    frame = requestAnimationFrame(measure);
    const disconnect = observePlacement(root, schedule);
    return () => {
      disconnect();
      if (timer !== null) clearTimeout(timer);
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [enabled, root, preferredLeft, preferredTop, compactPolicy, protectHeadings]);
  return enabled ? placement : EMPTY;
}
