'use client';

import { useEffect } from 'react';

/**
 * Last-resort boundary: an error thrown by the ROOT layout itself.
 *
 * When this renders, `[lng]/layout.tsx` has failed — which means no `<html>`,
 * no `<body>`, no theme, no i18n provider and no design tokens. Next requires
 * this file to supply the document element itself, and that is exactly why it
 * must depend on NOTHING: importing a translated string, a token-styled
 * component or a provider would make the fallback fail for the same reason the
 * page did.
 *
 * Hence the untranslated copy and the inline styles. It is not a shortcut —
 * a localised, themed error page is unreachable at this level, and pretending
 * otherwise would leave users with a blank screen instead of a plain one.
 * The theme-aware bit that IS safe is `color-scheme`, which lets the browser
 * paint its own light/dark ground rather than forcing white on a dark desktop.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // `logger` lives behind the app's module graph, which is precisely what may
    // have failed here — the console is the only sink guaranteed to exist.
    console.error('global_error', { digest: error.digest, message: error.message });
  }, [error]);

  return (
    <html lang="en" style={{ colorScheme: 'light dark' }}>
      <body
        style={{
          margin: 0,
          minHeight: '100dvh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'system-ui, sans-serif',
          padding: '1rem',
        }}
      >
        <main style={{ maxWidth: '28rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.5rem' }}>
            Something went wrong
          </h1>
          <p style={{ margin: '0 0 1.5rem', opacity: 0.75, lineHeight: 1.5 }}>
            The application could not start. Reloading usually clears it.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              font: 'inherit',
              padding: '0.5rem 1.25rem',
              borderRadius: '0.5rem',
              border: '1px solid currentColor',
              background: 'transparent',
              color: 'inherit',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
