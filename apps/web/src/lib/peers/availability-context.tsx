'use client';

/**
 * Whether connections are offered where a page renders its cards and bubbles.
 *
 * Read ONCE by the page (the chat, the generated-files gallery) from the app
 * configuration (`peersAvailable`) and handed down: every image card or answer
 * bubble asking `/config` for itself would cost one request each — the share
 * menu once cost 120 requests on a twelve-answer conversation. Every action that
 * needs a connection reads it: sharing a generated image (ADR-316) and relaying
 * an answer. Outside the provider the context is inert — a surface rendered in
 * isolation (a test, an archived read-only view) offers no such action.
 */

import * as React from 'react';

const PeersAvailabilityContext = React.createContext(false);

export interface PeersAvailabilityProviderProps {
  /** Connections are offered on this instance (`peersAvailable`). */
  available: boolean;
  children: React.ReactNode;
}

export function PeersAvailabilityProvider({ available, children }: PeersAvailabilityProviderProps) {
  return (
    <PeersAvailabilityContext.Provider value={available}>{children}</PeersAvailabilityContext.Provider>
  );
}

/** Whether an action needing a connection may be offered here. */
export function usePeersAvailable(): boolean {
  return React.useContext(PeersAvailabilityContext);
}
