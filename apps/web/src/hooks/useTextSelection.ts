'use client';

/**
 * useTextSelection — the C-02 selection reader.
 *
 * Watches `selectionchange` (debounced: the event fires on every caret move)
 * and exposes the current selection IF it lives entirely inside ONE
 * `[data-selection-scope="assistant"]` container — a selection spanning two
 * assistant bubbles, or leaking into user messages / page chrome, reads as
 * null. Built on useSyncExternalStore: the DOM selection is an external
 * store, and this shape needs no setState-in-effect.
 */

import { useSyncExternalStore } from 'react';

/** Marker attribute — ChatMessage stamps it on each assistant bubble body. */
export const SELECTION_SCOPE_SELECTOR = '[data-selection-scope="assistant"]';

/** Below this, a "selection" is a slipped double-click, not a passage. */
export const SELECTION_MIN_LENGTH = 3;

/** Debounce for selectionchange — it fires continuously while dragging. */
const SELECTION_DEBOUNCE_MS = 250;

export interface TextSelectionSnapshot {
  /** The selected text, trimmed. */
  text: string;
  /** Viewport-relative bounding rect of the selection (popover anchor). */
  rect: { top: number; left: number; width: number; bottom: number };
}

function scopeOf(node: Node | null): Element | null {
  const element = node instanceof Element ? node : (node?.parentElement ?? null);
  return element?.closest(SELECTION_SCOPE_SELECTOR) ?? null;
}

/** Clip the selection to its scrollports, keeping hidden lines out of the anchor. */
function visibleSelectionRect(rect: DOMRect, scope: Element, doc: Document) {
  let { top, left, bottom, right } = rect;
  for (let element: Element | null = scope; element; element = element.parentElement) {
    const style = doc.defaultView?.getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    if (/(auto|scroll|hidden|clip)/.test(style?.overflowY || style?.overflow || '')) {
      top = Math.max(top, bounds.top);
      bottom = Math.min(bottom, bounds.bottom);
    }
    if (/(auto|scroll|hidden|clip)/.test(style?.overflowX || style?.overflow || '')) {
      left = Math.max(left, bounds.left);
      right = Math.min(right, bounds.right);
    }
  }
  return bottom < top || right < left ? null : { top, left, width: right - left, bottom };
}

/**
 * Pure reader: the current document selection as a snapshot, or null when it
 * is collapsed, too short, outside the scope, or spanning several scopes.
 * Exported for direct unit testing (the hook is subscribe + cache glue).
 */
export function readScopedSelection(doc: Document): TextSelectionSnapshot | null {
  const selection = doc.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const text = selection.toString().trim();
  if (text.length < SELECTION_MIN_LENGTH) return null;
  const range = selection.getRangeAt(0);
  const startScope = scopeOf(range.startContainer);
  const endScope = scopeOf(range.endContainer);
  // Outside the assistant bubbles, or spanning TWO of them: not ours.
  if (!startScope || startScope !== endScope) return null;
  // A long selection can extend past the chat's scrollport. Anchor only to
  // the visible portion, so its hidden lines cannot push the menu offscreen.
  const rect = visibleSelectionRect(range.getBoundingClientRect(), startScope, doc);
  return rect ? { text, rect } : null;
}

function subscribe(onStoreChange: () => void): () => void {
  let timer: number | undefined;
  const onChange = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(onStoreChange, SELECTION_DEBOUNCE_MS);
  };
  document.addEventListener('selectionchange', onChange);
  document.addEventListener('scroll', onStoreChange, true);
  window.addEventListener('resize', onStoreChange);
  const viewport = window.visualViewport;
  viewport?.addEventListener('resize', onStoreChange);
  viewport?.addEventListener('scroll', onStoreChange);
  return () => {
    window.clearTimeout(timer);
    document.removeEventListener('selectionchange', onChange);
    document.removeEventListener('scroll', onStoreChange, true);
    window.removeEventListener('resize', onStoreChange);
    viewport?.removeEventListener('resize', onStoreChange);
    viewport?.removeEventListener('scroll', onStoreChange);
  };
}

// getSnapshot must return a REFERENTIALLY stable value for an unchanged
// selection, or useSyncExternalStore loops. One module-level cache is enough:
// a document has one selection, and one SelectionActions instance is mounted.
let cachedKey = '';
let cachedValue: TextSelectionSnapshot | null = null;

function getSnapshot(): TextSelectionSnapshot | null {
  const fresh = readScopedSelection(document);
  const key = fresh
    ? `${fresh.text}|${fresh.rect.top}|${fresh.rect.left}|${fresh.rect.width}|${fresh.rect.bottom}`
    : '';
  if (key !== cachedKey) {
    cachedKey = key;
    cachedValue = fresh;
  }
  return cachedValue;
}

function getServerSnapshot(): TextSelectionSnapshot | null {
  return null;
}

export function useTextSelection(): TextSelectionSnapshot | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
