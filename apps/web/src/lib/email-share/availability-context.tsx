'use client';

/**
 * Whether « Send by e-mail » is offered where a page renders its cards (ADR-321).
 *
 * Read ONCE by the page (the chat, the generated-files gallery) from the app
 * configuration (`emailShareAvailable`) and handed down, like the connections'
 * availability: every card asking `/config` for itself would cost a request
 * each. Outside the provider the context is inert — a surface rendered in
 * isolation offers no such action.
 */

import * as React from 'react';

const EmailShareAvailabilityContext = React.createContext(false);

export interface EmailShareAvailabilityProviderProps {
  /** Sending by e-mail is offered on this instance (`emailShareAvailable`). */
  available: boolean;
  children: React.ReactNode;
}

export function EmailShareAvailabilityProvider({
  available,
  children,
}: EmailShareAvailabilityProviderProps) {
  return (
    <EmailShareAvailabilityContext.Provider value={available}>
      {children}
    </EmailShareAvailabilityContext.Provider>
  );
}

/** Whether a « Send by e-mail » action may be offered here. */
export function useEmailShareAvailable(): boolean {
  return React.useContext(EmailShareAvailabilityContext);
}
