'use client';

import { useEffect, useState, type RefObject } from 'react';
import { unobstructedPlacement } from './eyes-placement';
import type { AnchorPosition } from './useEyesAnchor';

interface Placement {
  position: AnchorPosition | null;
  blocked: boolean;
}
const EMPTY: Placement = { position: null, blocked: false };
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

/** Bounded layout observations: no storage write, gesture change or synthetic click. */
export function useEyesAvoidance(root: RefObject<HTMLDivElement | null>, enabled: boolean) {
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
      const obstacles = [...document.querySelectorAll<HTMLElement>(CONTROLS)]
        .filter(control => !widget.contains(control))
        .map(control => control.getBoundingClientRect())
        .filter(box => box.width > 0 && box.height > 0 && box.bottom > 0 && box.top < innerHeight);
      const safe = unobstructedPlacement(
        { left: occupied.left, top: occupied.top },
        occupied,
        {
          width: innerWidth,
          height: innerHeight,
          minimumTop:
            document.querySelector('.lia-dashboard-header')?.getBoundingClientRect().bottom ?? 8,
        },
        obstacles
      );
      const position = safe
        ? { left: safe.left + rect.left - occupied.left, top: safe.top + rect.top - occupied.top }
        : null;
      setPlacement(previous =>
        previous.position?.left === position?.left &&
        previous.position?.top === position?.top &&
        previous.blocked === (position === null)
          ? previous
          : { position, blocked: position === null }
      );
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
    window.addEventListener('resize', schedule);
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
      window.removeEventListener('scroll', schedule, true);
      resize.disconnect();
      mutation.disconnect();
      if (timer !== null) clearTimeout(timer);
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [enabled, root]);
  return enabled ? placement : EMPTY;
}
