'use client';
/** The application's single selection observer; a bubble owns its snapshot until dismissed. */
import { useEffect } from 'react';
import { captureSelection, sameSelection } from '@/lib/selection-assist/targets';
import type { SelectionStore } from '@/lib/selection-assist/store';

function insideAssist(target: EventTarget | null): boolean {
  return target instanceof Element && !!target.closest('[data-selection-assist-ui]');
}

export function useSelectionAssistTarget(
  store: SelectionStore,
  enabled: boolean,
  allowCaret = false
): void {
  useEffect(() => {
    if (!enabled) return;
    let composing = false;
    let extendingWithKeyboard = false;
    const pointers = new Map<number, string>();
    let touches = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const capture = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (
          composing ||
          extendingWithKeyboard ||
          pointers.size > 0 ||
          touches > 0 ||
          insideAssist(document.activeElement)
        )
          return;
        const target = captureSelection(document, allowCaret);
        const previous = store.getSnapshot();
        if (sameSelection(target, previous)) return;
        store.capture(target);
      }, 180);
    };
    const start = (event: CompositionEvent) => {
      if (insideAssist(event.target)) return;
      composing = true;
      store.set(null);
    };
    const end = (event: CompositionEvent) => {
      if (insideAssist(event.target)) return;
      composing = false;
      capture();
    };
    const reachMenu = (event: KeyboardEvent) => {
      if (!insideAssist(event.target)) store.beginInteraction();
      if (event.key === 'Shift' && !insideAssist(event.target)) {
        extendingWithKeyboard = true;
        clearTimeout(timer);
        store.set(null);
      }
      if (!event.altKey || event.key !== 'Enter' || !store.getSnapshot()) return;
      const first = document.querySelector<HTMLElement>(
        '[data-selection-assist-ui][role="toolbar"] button'
      );
      if (first) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    const outside = (event: PointerEvent) => {
      if (insideAssist(event.target)) return;
      store.beginInteraction();
      pointers.set(event.pointerId, event.pointerType);
      clearTimeout(timer);
      store.set(null);
    };
    const release = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (!insideAssist(event.target)) capture();
    };
    const touchStarted = (event: TouchEvent) => {
      if (insideAssist(event.target)) return;
      store.beginInteraction();
      touches = event.touches.length;
      clearTimeout(timer);
      store.set(null);
    };
    const touchFinished = (event: TouchEvent) => {
      touches = event.touches.length;
      if (touches > 0) return;
      // Native selection can consume the pointer's terminal event. Touch release
      // is independent evidence; it must never retire a held mouse or pen.
      for (const [id, type] of pointers) if (type === 'touch') pointers.delete(id);
      if (!insideAssist(event.target)) capture();
    };
    const keyReleased = (event: KeyboardEvent) => {
      if (!event.shiftKey) extendingWithKeyboard = false;
      capture();
    };
    const enterFocus = (event: FocusEvent) => {
      const target = store.getSnapshot();
      if (
        target?.mode === 'edit' &&
        !insideAssist(event.target) &&
        event.target instanceof Node &&
        !target.element.contains(event.target)
      )
        store.dismiss('focus');
      capture();
    };
    const leaveEditor = (event: FocusEvent) => {
      const target = store.getSnapshot();
      if (target?.mode !== 'edit' || insideAssist(event.relatedTarget)) return;
      if (event.relatedTarget instanceof Node && target.element.contains(event.relatedTarget))
        return;
      clearTimeout(timer);
      if (insideAssist(event.target) && !event.relatedTarget) {
        // A submitted form can remove its focused control before the response's
        // layout effect focuses the close button. Judge the settled destination.
        queueMicrotask(() => {
          if (store.getSnapshot() !== target || insideAssist(document.activeElement)) return;
          if (target.element.contains(document.activeElement)) return;
          store.dismiss('focus');
        });
        return;
      }
      store.dismiss('focus');
    };
    const abandon = () => {
      pointers.clear();
      touches = 0;
      extendingWithKeyboard = false;
      clearTimeout(timer);
      if (store.getSnapshot()?.mode === 'edit') store.dismiss('focus');
      // Starting a gesture already clears its target. A completed reading
      // selection (and any answer using it) survives switching windows.
    };
    const cancelPointer = (event: PointerEvent) => {
      if (!pointers.delete(event.pointerId)) return;
      clearTimeout(timer);
      store.set(null);
    };
    document.addEventListener('selectionchange', capture, true);
    document.addEventListener('select', capture, true);
    document.addEventListener('focusin', enterFocus);
    document.addEventListener('focusout', leaveEditor);
    document.addEventListener('input', capture);
    document.addEventListener('pointerup', release, true);
    document.addEventListener('pointercancel', cancelPointer, true);
    document.addEventListener('touchstart', touchStarted, { capture: true, passive: true });
    document.addEventListener('touchend', touchFinished, { capture: true, passive: true });
    document.addEventListener('touchcancel', touchFinished, { capture: true, passive: true });
    document.addEventListener('keyup', keyReleased);
    document.addEventListener('keydown', reachMenu);
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('compositionstart', start);
    document.addEventListener('compositionend', end);
    window.addEventListener('blur', abandon);
    // Metadata may arrive after an input has already taken focus.
    if (allowCaret) capture();
    return () => {
      clearTimeout(timer);
      store.set(null);
      document.removeEventListener('selectionchange', capture, true);
      document.removeEventListener('select', capture, true);
      document.removeEventListener('focusin', enterFocus);
      document.removeEventListener('focusout', leaveEditor);
      document.removeEventListener('input', capture);
      document.removeEventListener('pointerup', release, true);
      document.removeEventListener('pointercancel', cancelPointer, true);
      document.removeEventListener('touchstart', touchStarted, true);
      document.removeEventListener('touchend', touchFinished, true);
      document.removeEventListener('touchcancel', touchFinished, true);
      document.removeEventListener('keyup', keyReleased);
      document.removeEventListener('keydown', reachMenu);
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('compositionstart', start);
      document.removeEventListener('compositionend', end);
      window.removeEventListener('blur', abandon);
    };
  }, [store, enabled, allowCaret]);
}
