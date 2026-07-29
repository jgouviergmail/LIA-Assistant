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
  const rect = range.getBoundingClientRect();
  return {
    text,
    rect: { top: rect.top, left: rect.left, width: rect.width, bottom: rect.bottom },
  };
}

function subscribe(onStoreChange: () => void): () => void {
  let timer: number | undefined;
  const onChange = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(onStoreChange, SELECTION_DEBOUNCE_MS);
  };
  document.addEventListener('selectionchange', onChange);
  return () => {
    window.clearTimeout(timer);
    document.removeEventListener('selectionchange', onChange);
  };
}

// getSnapshot must return a REFERENTIALLY stable value for an unchanged
// selection, or useSyncExternalStore loops. One module-level cache is enough:
// a document has one selection, and one SelectionActions instance is mounted.
let cachedKey = '';
let cachedValue: TextSelectionSnapshot | null = null;

function getSnapshot(): TextSelectionSnapshot | null {
  const fresh = readScopedSelection(document);
  const key = fresh ? `${fresh.text}|${fresh.rect.top}|${fresh.rect.left}` : '';
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
