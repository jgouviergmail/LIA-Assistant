'use client';

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { MessageScrollStore } from './message-scroll-store';

/** DOM reading position belongs to the owner, beyond a private portal's lifetime. */
export function useMessageLogScroll(
  messages: ReadonlyArray<{ readonly id: string }>,
  position?: MessageScrollStore
) {
  const scroller = useRef<HTMLDivElement>(null);
  const restoring = useRef(false);
  const [local] = useState(() => new MessageScrollStore());
  const store = position ?? local;
  const anchored = useSyncExternalStore(store.subscribe, store.getAnchored, store.getAnchored);
  useLayoutEffect(() => {
    const node = scroller.current;
    if (!node) return;
    const restore = () => {
      const current = store.read();
      if (current.anchored) {
        restoring.current = false;
        node.scrollTop = node.scrollHeight;
        store.remember({ anchored: true, top: node.scrollTop });
        return;
      }
      restoring.current = true;
      node.scrollTop = current.top;
      // A visible portal can still have a temporary unclamped height. Never
      // replace its saved history with the browser's resulting zero offset.
      restoring.current = node.clientHeight === 0 || Math.abs(node.scrollTop - current.top) >= 1;
    };
    restore();
    const frame = requestAnimationFrame(restore);
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(restore) : null;
    observer?.observe(node);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      restoring.current = false;
    };
  }, [store]);
  useEffect(() => {
    const node = scroller.current;
    if (!node || !anchored) return;
    node.scrollTop = node.scrollHeight;
    store.remember({ anchored: true, top: node.scrollTop });
  }, [messages, anchored, store]);
  function remember(node: HTMLDivElement) {
    if (restoring.current || node.clientHeight === 0) return;
    const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 60;
    store.remember({ anchored: atBottom, top: node.scrollTop });
  }
  function latest() {
    const node = scroller.current;
    if (!node) return;
    restoring.current = false;
    node.scrollTop = node.scrollHeight;
    store.remember({ anchored: true, top: node.scrollTop });
    node.focus({ preventScroll: true });
  }
  return { scroller, anchored, remember, latest };
}
