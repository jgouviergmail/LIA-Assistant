import { useCallback, useState } from 'react';

import { useAuthFeatures } from '@/hooks/useWebAuthn';
import { SUBMITS_WITHOUT_WIDGET, type TurnstileAction } from '@/lib/turnstile';

/** What a password form needs from the bot check (ADR-364). */
export interface TurnstileDoor {
  /** The instance's site key, or null when it runs no bot check. */
  siteKey: string | null;
  /** The token the widget produced, or null. */
  token: string | null;
  /** Whether the widget could not load (or reported an error) and has no token since. */
  failed: boolean;
  /**
   * Whether the form may submit: no check to pass, a token in hand, or — at the
   * sign-in door alone — a widget that could not load.
   */
  ready: boolean;
  /** Hand to the widget's `onToken`. */
  onToken: (token: string | null) => void;
  /** Hand to the widget's `onFailure`. */
  onFailure: () => void;
  /** Hand to the widget's `resetSignal`. */
  resetSignal: number;
  /** Call after a submit: the API spent the token, the widget makes a new one. */
  spent: () => void;
}

/**
 * The bot check of a password door, as one value the form reads.
 *
 * While the capabilities are loading the form is not held back: the API is
 * the authority and refuses a door it guards when no token comes. Once the
 * widget could not load, the sign-in may go without a token (the API decides
 * from its own view of Cloudflare); a sign-up or a reset request waits.
 *
 * @param action - The door this form is.
 * @returns The door's state and its callbacks.
 */
export function useTurnstileDoor(action: TurnstileAction): TurnstileDoor {
  const { features } = useAuthFeatures();
  const siteKey = features?.turnstile_site_key ?? null;
  const [token, setToken] = useState<string | null>(null);
  const [widgetFailed, setWidgetFailed] = useState(false);
  const [resetSignal, setResetSignal] = useState(0);
  const spent = useCallback(() => setResetSignal(signal => signal + 1), []);
  const onToken = useCallback((next: string | null) => {
    setToken(next);
    if (next) setWidgetFailed(false);
  }, []);
  const onFailure = useCallback(() => setWidgetFailed(true), []);
  return {
    siteKey,
    token,
    failed: widgetFailed,
    ready:
      siteKey === null || token !== null || (widgetFailed && SUBMITS_WITHOUT_WIDGET.has(action)),
    onToken,
    onFailure,
    resetSignal,
    spent,
  };
}
