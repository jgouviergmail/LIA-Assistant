import { useEffect, useRef, useState, type KeyboardEvent } from 'react';

function targetCell(key: string, index: number, columns: number, count: number): number | null {
  const rowStart = index - (index % columns);
  if (key === 'Home') return rowStart;
  if (key === 'End') return Math.min(count - 1, rowStart + columns - 1);
  const offsets: Record<string, number | undefined> = { ArrowLeft: -1, ArrowRight: 1 };
  if (count > columns) {
    offsets.ArrowUp = -columns;
    offsets.ArrowDown = columns;
  }
  const offset = offsets[key];
  return offset === undefined ? null : (index + offset + count) % count;
}
export function useBoardFocus(count: number, columns: number, isCurrent: () => boolean) {
  const nodes = useRef<(HTMLButtonElement | null)[]>([]);
  const [focused, setFocused] = useState(0);
  // A new board takes the keyboard once. A reveal or a re-render never pulls the
  // focus back to the first cell from wherever the person has moved it.
  const placed = useRef(false);
  useEffect(() => {
    if (placed.current || !isCurrent()) return;
    placed.current = true;
    nodes.current[0]?.focus({ preventScroll: true });
  }, [isCurrent]);
  function keyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!isCurrent() || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.repeat && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    const next = targetCell(event.key, index, columns, count);
    if (next === null) return;
    event.preventDefault();
    event.stopPropagation();
    nodes.current[next]?.focus();
  }
  return { nodes, focused, setFocused, keyDown };
}
