'use client';

/**
 * InstallHint — contextual PWA install nudge (UXR Lot 9, A6; PortraitHint
 * pattern: exported pure visibility rule + localStorage dismissal).
 *
 * Shows a discreet dashboard line after ≥3 visits, never in standalone
 * display-mode, dismissible forever. Chromium: uses the captured
 * `beforeinstallprompt` for a real install prompt; iOS Safari (no event):
 * shows the "Share → Add to Home Screen" instruction instead.
 *
 * Hooks discipline: the environment snapshot (visits, dismissal, standalone,
 * iOS) is captured ONCE in a useState initializer (render-time read, no
 * state-sync effect); the only effect is write/subscribe-only (persist the
 * bumped counter + listen for beforeinstallprompt — setState happens in the
 * event LISTENER, the standard subscription pattern).
 */

import { useEffect, useRef, useState } from 'react';
import { MonitorDown, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  PWA_INSTALL_HINT_DISMISSED_KEY,
  PWA_INSTALL_HINT_MIN_VISITS,
  PWA_INSTALL_HINT_VISITS_KEY,
} from '@/lib/constants';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
}

/** Pure visibility rule — exported for direct testing. */
export function isInstallHintVisible(args: {
  visits: number;
  dismissed: boolean;
  standalone: boolean;
}): boolean {
  return !args.dismissed && !args.standalone && args.visits >= PWA_INSTALL_HINT_MIN_VISITS;
}

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private mode — the hint simply stays session-local.
  }
}

/** One-shot environment snapshot (client only — SSR renders nothing). */
function snapshotEnvironment() {
  if (typeof window === 'undefined') {
    return { visits: 0, dismissed: true, standalone: true, ios: false };
  }
  return {
    // The current visit counts — persisted by the write-only effect below.
    visits: Number(readStorage(PWA_INSTALL_HINT_VISITS_KEY) ?? '0') + 1,
    dismissed: readStorage(PWA_INSTALL_HINT_DISMISSED_KEY) === 'true',
    standalone: window.matchMedia('(display-mode: standalone)').matches,
    ios: /iphone|ipad|ipod/i.test(window.navigator.userAgent),
  };
}

export function InstallHint() {
  const { t } = useTranslation();
  const [env] = useState(snapshotEnvironment);
  const [dismissedNow, setDismissedNow] = useState(false);
  // True once Chromium offered its install prompt (set in the LISTENER).
  const [canPrompt, setCanPrompt] = useState(false);
  const promptRef = useRef<BeforeInstallPromptEvent | null>(null);

  // Write/subscribe-only effect: persist the bumped visit counter and capture
  // the Chromium install prompt. No direct setState in the effect body.
  useEffect(() => {
    writeStorage(PWA_INSTALL_HINT_VISITS_KEY, String(env.visits));
    const onPrompt = (event: Event) => {
      event.preventDefault();
      promptRef.current = event as BeforeInstallPromptEvent;
      setCanPrompt(true);
    };
    window.addEventListener('beforeinstallprompt', onPrompt);
    return () => window.removeEventListener('beforeinstallprompt', onPrompt);
  }, [env.visits]);

  if (dismissedNow || !isInstallHintVisible(env)) return null;

  const dismiss = () => {
    writeStorage(PWA_INSTALL_HINT_DISMISSED_KEY, 'true');
    setDismissedNow(true);
  };

  const install = () => {
    void promptRef.current?.prompt();
    dismiss();
  };

  return (
    <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
      <MonitorDown className="h-4 w-4 shrink-0 text-primary/70" aria-hidden />
      {env.ios || !canPrompt ? (
        <span>{t('dashboard.install_hint.ios_text')}</span>
      ) : (
        <>
          <span>{t('dashboard.install_hint.text')}</span>
          <button
            type="button"
            onClick={install}
            className="font-semibold text-primary hover:text-primary/80 underline decoration-primary/40 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {t('dashboard.install_hint.cta')}
          </button>
        </>
      )}
      <button
        type="button"
        onClick={dismiss}
        aria-label={t('dashboard.install_hint.dismiss')}
        className="p-1 rounded-full hover:bg-muted"
      >
        <X className="h-3.5 w-3.5" aria-hidden />
      </button>
    </div>
  );
}
