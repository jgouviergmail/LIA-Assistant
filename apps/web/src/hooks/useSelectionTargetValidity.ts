'use client';
/** One invalidation observer for an answer or recording bound to a native text snapshot. */
import { useEffect, useEffectEvent } from 'react';
import { targetIsCurrent, type SelectionTarget } from '@/lib/selection-assist/targets';

export function useSelectionTargetValidity(
  target: SelectionTarget,
  onChanged: () => void,
  onDetached: () => void
): void {
  const changed = useEffectEvent(onChanged);
  const detached = useEffectEvent(onDetached);
  useEffect(() => {
    const check = () => {
      if (!target.element.isConnected) detached();
      else if (!targetIsCurrent(target)) changed();
    };
    const observer = new MutationObserver(records => {
      if (
        !target.element.isConnected ||
        records.some(record => target.element.contains(record.target))
      )
        check();
    });
    observer.observe(document.body, { subtree: true, childList: true });
    observer.observe(target.element, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
    });
    target.element.addEventListener('input', check);
    return () => {
      observer.disconnect();
      target.element.removeEventListener('input', check);
    };
  }, [target]);
}
