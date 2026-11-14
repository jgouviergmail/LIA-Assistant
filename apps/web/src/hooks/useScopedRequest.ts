'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';

/** Retire every read when its owner/discussion/generation changes, even if fetch ignores abort. */
export function useScopedRequest(key: string) {
  // Identity, not just key equality: A → B → A must not revive A's old callbacks.
  const lifetime = useMemo(() => Symbol(key), [key]);
  const current = useRef<{ lifetime: symbol; controller: AbortController } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    current.current = { lifetime, controller };
    return () => {
      controller.abort();
      current.current = null;
    };
  }, [lifetime]);

  return useCallback(
    async <T>(read: (signal: AbortSignal) => Promise<T>): Promise<T> => {
      const scope = current.current;
      if (scope?.lifetime !== lifetime || scope.controller.signal.aborted)
        throw new DOMException('Retired discussion', 'AbortError');
      const { controller } = scope;
      const result = await read(controller.signal);
      controller.signal.throwIfAborted();
      return result;
    },
    [lifetime]
  );
}
