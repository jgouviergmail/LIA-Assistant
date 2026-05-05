'use client';

/**
 * Cross-component cache invalidation for the LLM/image catalogue admin UI.
 *
 * Problem: ``AdminLLMPricingSection``, ``AdminImagePricingSection`` and
 * ``AdminLLMConfigSection`` are sibling components in the Settings page.
 * When the admin mutates a row in one of the Tarification panes, the
 * backend correctly invalidates its caches cross-worker (ADR-063), but
 * Configuration LLM has its own React-state copy of
 * ``GET /llm-config/metadata`` and never refetches — so the dropdown
 * stays stale until the page is reloaded.
 *
 * Solution: a tiny React Context where consumers (Configuration LLM)
 * register a refetch handler keyed by cache name, and emitters
 * (Tarification panes) call ``invalidate(name)`` to fire all matching
 * handlers.
 *
 * The ``cacheName`` keys mirror the backend's ``CACHE_NAME_*``
 * constants (``model_capabilities``, ``image_generation_options``) so
 * the mental model is uniform across server and client.
 *
 * Scope: only the Settings admin sub-tree is wrapped with the provider.
 * The Context returns a no-op invalidator outside the provider so other
 * pages don't need to opt in.
 */

import * as React from 'react';

/**
 * Cache identifier — must stay aligned with the backend ``CACHE_NAME_*``
 * constants in ``apps/api/src/core/constants.py``.
 */
export type CatalogueCacheName = 'model_capabilities' | 'image_generation_options';

type Handler = () => void | Promise<void>;

interface CatalogueInvalidationContextValue {
  register(name: CatalogueCacheName, handler: Handler): () => void;
  invalidate(name: CatalogueCacheName): void;
}

// Default value: a no-op implementation so consumers used outside the
// provider don't crash (e.g. in unit tests rendering a single component).
const NOOP_VALUE: CatalogueInvalidationContextValue = {
  register: () => () => undefined,
  invalidate: () => undefined,
};

const CatalogueInvalidationContext =
  React.createContext<CatalogueInvalidationContextValue>(NOOP_VALUE);

/**
 * Wraps a sub-tree to enable cross-sibling cache invalidation. Place at
 * the level of the Settings admin block.
 */
export function CatalogueInvalidationProvider({ children }: { children: React.ReactNode }) {
  // Each cache name maps to a Set of handlers (multiple consumers may
  // listen, e.g. if a future component also depends on the catalogue).
  const handlersRef = React.useRef<Map<CatalogueCacheName, Set<Handler>>>(new Map());

  const value = React.useMemo<CatalogueInvalidationContextValue>(
    () => ({
      register(name, handler) {
        let bucket = handlersRef.current.get(name);
        if (!bucket) {
          bucket = new Set();
          handlersRef.current.set(name, bucket);
        }
        bucket.add(handler);
        return () => {
          bucket?.delete(handler);
        };
      },
      invalidate(name) {
        const bucket = handlersRef.current.get(name);
        if (!bucket) return;
        // Fire all handlers; failures in one don't block the others.
        bucket.forEach(h => {
          try {
            const result = h();
            if (result && typeof (result as Promise<void>).catch === 'function') {
              (result as Promise<void>).catch(() => {
                // handler is responsible for its own error reporting
              });
            }
          } catch {
            // Same: swallow so siblings still fire.
          }
        });
      },
    }),
    []
  );

  return (
    <CatalogueInvalidationContext.Provider value={value}>
      {children}
    </CatalogueInvalidationContext.Provider>
  );
}

/**
 * Consumer hook: register ``handler`` to run whenever a sibling emits
 * ``invalidate(cacheName)``. Cleanup on unmount via ``useEffect``.
 *
 * The handler is wrapped in a ref so callers can pass an inline closure
 * without re-registering on every render.
 */
export function useCatalogueInvalidationListener(
  cacheName: CatalogueCacheName,
  handler: Handler
): void {
  const ctx = React.useContext(CatalogueInvalidationContext);
  const handlerRef = React.useRef(handler);
  React.useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  React.useEffect(() => {
    return ctx.register(cacheName, () => handlerRef.current());
  }, [ctx, cacheName]);
}

/**
 * Emitter hook: returns the ``invalidate`` function. Stable reference —
 * safe to call from event handlers without dependency changes.
 */
export function useCatalogueInvalidator(): (name: CatalogueCacheName) => void {
  const ctx = React.useContext(CatalogueInvalidationContext);
  return ctx.invalidate;
}
