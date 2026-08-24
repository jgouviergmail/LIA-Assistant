'use client';

/**
 * Where a native shell lands after a provider sign-in.
 *
 * OAuth cannot run inside a WebView, so the flow left for the system browser.
 * The operating system handed the shell a `lia://auth-callback?code=…` deep
 * link, and the shell navigated this WebView here — the only place that holds
 * the verifier the code is bound to.
 *
 * Nothing is shown for long: this page spends the code and moves on. It exists
 * because the exchange must happen from the WebView's own cookie jar, which the
 * browser's could never be.
 */

import { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/hooks/useAuth';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { logger } from '@/lib/logger';
import { takeNativeVerifier } from '@/lib/native/shell';

function NativeAuthContent() {
  const router = useLocalizedRouter();
  const searchParams = useSearchParams();
  const { completeNativeSignIn } = useAuth();
  const { t } = useTranslation();
  // Derived, not stored: whether a code arrived is knowable at render, and
  // deciding it in the effect would be a setState the hooks ratchet rightly
  // refuses.
  const code = searchParams.get('code');
  const [exchangeFailed, setExchangeFailed] = useState(false);

  // The code is single-use and so is the verifier: React may run an effect
  // twice in development, and the second attempt would spend a code that is
  // already gone and report a failure that never happened.
  const started = useRef(false);

  useEffect(() => {
    if (!code || started.current) return;
    started.current = true;

    // Everything that can go wrong ends in the same place. Reading the
    // verifier inside the chain keeps a missing one from becoming a second,
    // synchronous failure path saying the same thing.
    Promise.resolve()
      .then(() => {
        const verifier = takeNativeVerifier();
        if (!verifier) {
          // A deep link arriving with no sign-in in flight.
          throw new Error('no verifier for this handoff');
        }
        return completeNativeSignIn(code, verifier);
      })
      .then(({ mfaRequired }) => {
        router.push(mfaRequired ? '/login?mfa=1' : '/dashboard');
      })
      .catch((error: unknown) => {
        logger.error('native_sign_in_failed', error as Error, { component: 'NativeAuthPage' });
        setExchangeFailed(true);
      });
  }, [code, completeNativeSignIn, router]);

  if (!code || exchangeFailed) {
    return (
      <div className="text-center space-y-4">
        <p className="text-sm text-muted-foreground">{t('auth.oauth.error_message')}</p>
        <button
          type="button"
          onClick={() => router.push('/login')}
          className="text-sm font-semibold text-primary underline underline-offset-4"
        >
          {t('auth.mfa.back_to_login')}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 py-12">
      <LoadingSpinner />
      <p className="text-sm text-muted-foreground">{t('auth.oauth.connecting')}</p>
    </div>
  );
}

export default function NativeAuthPage() {
  // `useSearchParams` needs a boundary or the production build fails
  // prerendering this route — the same requirement `/{lng}/share` documents.
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <NativeAuthContent />
    </Suspense>
  );
}
