/** Native text targets. A snapshot authorizes one plain-text replacement, never an HTML write. */
import type { SelectionRect } from '@/lib/selection-position';
import { generateUUID } from '@/lib/utils';

const EXCLUDED =
  '[data-selection-assist="off"], [inert], [aria-hidden="true"], input[type="password"], [autocomplete="one-time-code"], [autocomplete="current-password"], [autocomplete="new-password"], iframe, canvas, script, style';
const SURFACE = '[data-selection-surface], [data-selection-owner], [data-selection-host]';
type Field = HTMLInputElement | HTMLTextAreaElement;
interface BaseTarget {
  id: string;
  mode: 'read' | 'edit';
  text: string;
  rect: SelectionRect;
  element: HTMLElement;
  host: string | null;
  revision: string;
}
export type SelectionTarget = BaseTarget &
  (
    | { kind: 'field'; element: Field; start: number; end: number }
    | { kind: 'range'; range: Range; rangeText: string; rich: boolean }
  );
export type ApplyResult = 'applied' | 'stale' | 'too_long' | 'unsupported';

/** Restore keyboard continuity to the source, including a span inside a focusable reader. */
export function focusSelectionTarget(target: SelectionTarget): void {
  if (!target.element.isConnected) return;
  const focusable = target.element.closest<HTMLElement>(
    '[tabindex], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled]), a[href], [contenteditable="true"], [contenteditable=""]'
  );
  if (focusable) {
    focusable.focus({ preventScroll: true });
    return;
  }
  target.element.setAttribute('tabindex', '-1');
  target.element.focus({ preventScroll: true });
  target.element.removeAttribute('tabindex');
}

function elementOf(node: Node | null): HTMLElement | null {
  return node instanceof HTMLElement ? node : (node?.parentElement ?? null);
}
function hostOf(element: HTMLElement): string | null {
  return element.closest('[data-selection-host]')?.getAttribute('data-selection-host') ?? null;
}
function readable(element: HTMLElement): boolean {
  return !element.closest(EXCLUDED);
}
function rectOf(rect: DOMRect): SelectionRect {
  return { top: rect.top, left: rect.left, width: rect.width, bottom: rect.bottom };
}
/** Empty text authorizes dictation only at the active editable caret, on either DOM surface. */
function hasTextOrFocusedCaret(text: string, caret: boolean, editor: HTMLElement | null): boolean {
  return !!text.trim() || (caret && !!editor?.contains(editor.ownerDocument.activeElement));
}
function captureField(element: Field, allowCaret: boolean): SelectionTarget | null {
  if (!readable(element) || element.disabled) return null;
  const start = element.selectionStart,
    end = element.selectionEnd;
  if (start === null || end === null) return null;
  const caret = allowCaret && start === end;
  const text = element.value.slice(start, end);
  if (!hasTextOrFocusedCaret(text, caret, element.readOnly ? null : element)) return null;
  return {
    id: generateUUID(),
    kind: 'field',
    mode: element.readOnly ? 'read' : 'edit',
    element,
    start,
    end,
    text,
    revision: element.value,
    rect: rectOf(element.getBoundingClientRect()),
    host: hostOf(element),
  };
}
function rangeIsReadable(range: Range, start: HTMLElement, end: HTMLElement): boolean {
  if (!readable(start) || !readable(end)) return false;
  if (start.closest(SURFACE) !== end.closest(SURFACE)) return false;
  const root = elementOf(range.commonAncestorContainer);
  return (
    !!root && !Array.from(root.querySelectorAll(EXCLUDED)).some(node => range.intersectsNode(node))
  );
}
function captureRange(document: Document, allowCaret: boolean): SelectionTarget | null {
  const selection = document.getSelection();
  if (!selection || selection.rangeCount !== 1) return null;
  const range = selection.getRangeAt(0);
  const start = elementOf(range.startContainer),
    end = elementOf(range.endContainer);
  if (!start || !end || !rangeIsReadable(range, start, end)) return null;
  const editor = start.closest<HTMLElement>('[contenteditable]');
  if (editor !== end.closest('[contenteditable]')) return null;
  const rich = !!editor && editor.getAttribute('contenteditable') !== 'false';
  const text = selection.toString();
  if (!hasTextOrFocusedCaret(text, allowCaret && selection.isCollapsed, rich ? editor : null))
    return null;
  const element = rich ? editor : elementOf(range.commonAncestorContainer);
  if (!element) return null;
  const rect = rangeRect(range, element);
  return {
    id: generateUUID(),
    kind: 'range',
    mode: rich ? 'edit' : 'read',
    range: range.cloneRange(),
    rangeText: range.toString(),
    rich,
    element,
    text,
    revision: element.innerHTML,
    rect: rectOf(rect),
    host: hostOf(element),
  };
}

export function captureSelection(document: Document, allowCaret = false): SelectionTarget | null {
  const active = document.activeElement;
  if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) {
    if (!readable(active)) return null;
    const field = captureField(active, allowCaret);
    return field?.text ? field : (captureRange(document, allowCaret) ?? field);
  }
  return captureRange(document, allowCaret);
}
export function sameSelection(
  left: SelectionTarget | null,
  right: SelectionTarget | null
): boolean {
  if (
    !left ||
    !right ||
    left.element !== right.element ||
    left.revision !== right.revision ||
    left.mode !== right.mode
  )
    return false;
  if (left.kind === 'field' && right.kind === 'field')
    return left.start === right.start && left.end === right.end;
  if (left.kind !== 'range' || right.kind !== 'range') return false;
  return (
    left.range.compareBoundaryPoints(Range.START_TO_START, right.range) === 0 &&
    left.range.compareBoundaryPoints(Range.END_TO_END, right.range) === 0
  );
}
export function targetIsCurrent(target: SelectionTarget): boolean {
  if (!target.element.isConnected || !readable(target.element)) return false;
  if (target.kind === 'field')
    return (
      !target.element.disabled &&
      !(target.mode === 'edit' && target.element.readOnly) &&
      target.element.value === target.revision
    );
  if (
    target.rich &&
    !['true', '', 'plaintext-only'].includes(
      target.element.getAttribute('contenteditable') ?? 'false'
    )
  )
    return false;
  return (
    target.element.innerHTML === target.revision && target.range.toString() === target.rangeText
  );
}

/** Explicit dismissal never reopens the same selection through a delayed selectionchange. */
export function dismissSelection(target: SelectionTarget): void {
  target.element.ownerDocument.getSelection()?.removeAllRanges();
  if (target.kind === 'field' && targetIsCurrent(target))
    target.element.setSelectionRange(target.end, target.end);
}

/** Re-measure the real target after its scrollport or the software keyboard moves. */
export function currentTargetRect(target: SelectionTarget): SelectionRect {
  if (target.kind === 'range') return rectOf(rangeRect(target.range, target.element));
  return rectOf(target.element.getBoundingClientRect());
}

/** Some rich selections expose no rectangle. Anchor to their field instead. */
function rangeRect(range: Range, element: HTMLElement): DOMRect {
  const rect =
    typeof range.getBoundingClientRect === 'function' ? range.getBoundingClientRect() : null;
  return rect && rect.height > 0 ? rect : element.getBoundingClientRect();
}
export function replacementFits(target: SelectionTarget, text: string): boolean {
  if (target.kind !== 'field' || target.element.maxLength < 0) return true;
  return (
    target.revision.length - (target.end - target.start) + text.length <= target.element.maxLength
  );
}
export function applySelection(target: SelectionTarget, text: string): ApplyResult {
  if (target.mode !== 'edit' || !targetIsCurrent(target)) return 'stale';
  if (!replacementFits(target, text)) return 'too_long';
  const document = target.element.ownerDocument;
  if (typeof document.execCommand !== 'function') return 'unsupported';
  target.element.focus({ preventScroll: true });
  if (target.kind === 'field') target.element.setSelectionRange(target.start, target.end);
  else {
    document.getSelection()?.removeAllRanges();
    document.getSelection()?.addRange(target.range.cloneRange());
  }
  // The native editing command preserves undo and emits the input event React/the editor owns.
  const applied = document.execCommand('insertText', false, text);
  if (!applied) return 'unsupported';
  if (
    target.kind === 'field' &&
    target.element.value !==
      target.revision.slice(0, target.start) + text + target.revision.slice(target.end)
  )
    return 'stale';
  return 'applied';
}
