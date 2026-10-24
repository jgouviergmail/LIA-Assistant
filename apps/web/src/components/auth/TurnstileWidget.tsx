'use client';

import { useEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import { useTranslation } from 'react-i18next';

import {
  SUBMITS_WITHOUT_WIDGET,
  loadTurnstile,
  turnstileLanguage,
  type TurnstileAction,
  type TurnstileApi,
} from '@/lib/turnstile';

interface TurnstileWidgetProps {
  /** The instance's public site key (`GET /auth/features`). */
  siteKey: string;
  /** The door this token is for — the API refuses a token made for another. */
  action: TurnstileAction;
  /** Receives the token, or null when there is none (yet, any more). */
  onToken: (token: string | null) => void;
  /** Told when the check could not load or reported an error. */
  onFailure: () => void;
  /** Incremented by the form after each submit: the API spent the token. */
  resetSignal: number;
}

/**
 * Cloudflare Turnstile's widget for one password door (ADR-364).
 *
 * `interaction-only`: most people never see it — it appears only when
 * Cloudflare wants an interaction. The token is single-use, so the form bumps
 * `resetSignal` after every submit and a fresh one is produced. When it cannot
 * load, the sign-in door says it can still be sent; the others say to reload.
 */
export function TurnstileWidget({
  siteKey,
  action,
  onToken,
  onFailure,
  resetSignal,
}: TurnstileWidgetProps) {
  const { t, i18n } = useTranslation();
  const { resolvedTheme } = useTheme();
  const container = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const turnstile = useRef<TurnstileApi | null>(null);
  const tokenSink = useRef(onToken);
  const failureSink = useRef(onFailure);
  const [failed, setFailed] = useState(false);
  const theme = resolvedTheme === 'dark' ? 'dark' : 'light';
  const language = turnstileLanguage(i18n.language);

  useEffect(() => {
    tokenSink.current = onToken;
    failureSink.current = onFailure;
  }, [onToken, onFailure]);

  useEffect(() => {
    let cancelled = false;
    const giveUp = () => {
      setFailed(true);
      tokenSink.current(null);
      failureSink.current();
    };
    loadTurnstile()
      .then(api => {
        if (cancelled || !container.current) return;
        turnstile.current = api;
        widgetId.current =
          api.render(container.current, {
            sitekey: siteKey,
            action,
            theme,
            language,
            size: 'flexible',
            appearance: 'interaction-only',
            callback: token => {
              setFailed(false);
              tokenSink.current(token);
            },
            'expired-callback': () => tokenSink.current(null),
            'error-callback': () => {
              giveUp();
              return true;
            },
          }) ?? null;
      })
      .catch(() => {
        if (!cancelled) giveUp();
      });
    return () => {
      cancelled = true;
      const id = widgetId.current;
      widgetId.current = null;
      if (id) turnstile.current?.remove(id);
    };
  }, [siteKey, action, theme, language]);

  useEffect(() => {
    if (resetSignal === 0) return;
    tokenSink.current(null);
    if (widgetId.current) turnstile.current?.reset(widgetId.current);
  }, [resetSignal]);

  return (
    <div role="group" aria-label={t('auth.turnstile.label')}>
      <div ref={container} />
      {failed && (
        <p className="text-sm text-destructive">
          {t(
            SUBMITS_WITHOUT_WIDGET.has(action)
              ? 'auth.turnstile.load_failed_sign_in'
              : 'auth.turnstile.load_failed'
          )}
        </p>
      )}
    </div>
  );
}
