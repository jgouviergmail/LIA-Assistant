/**
 * The web app's side of the native shells.
 *
 * This file deliberately imports **nothing** from Capacitor. The bridge injects
 * `window.Capacitor` into the page at document start, so detection and calls go
 * through that object — adding `@capacitor/core` to `apps/web` would put a
 * native dependency in a bundle that is, first and foremost, a website.
 *
 * What lives here is only what a browser genuinely cannot do: recognise that we
 * are inside a shell, and hand a URL to the system browser. Provider sign-in is
 * refused inside a WebView on both engines (`disallowed_useragent`), so the flow
 * has to leave the app — and the code that comes back is bound to a verifier
 * this module keeps, because the return trip rides a custom scheme any
 * application could claim (RFC 8252 §8.1).
 */

import { logger } from '@/lib/logger';

/** Where the verifier waits while the user is away in the system browser. */
const VERIFIER_KEY = 'lia.native.verifier';

/** RFC 7636 §4.1 — the bounds the API validates against. */
const VERIFIER_BYTES = 32;

interface ShellPlugin {
  openExternal(options: { url: string }): Promise<void>;
}

interface CapacitorGlobal {
  isNativePlatform?: () => boolean;
  Plugins?: { LiaShell?: ShellPlugin };
}

function capacitor(): CapacitorGlobal | undefined {
  return (window as unknown as { Capacitor?: CapacitorGlobal }).Capacitor;
}

/**
 * Whether this page is running inside one of LIA's native shells.
 *
 * @returns True in the shell, false in any browser — including a PWA, which is
 *   still a browser and keeps the ordinary redirect flow.
 */
export function isNativeShell(): boolean {
  if (typeof window === 'undefined') return false;
  return capacitor()?.isNativePlatform?.() === true;
}

/** Base64url, unpadded — the alphabet RFC 7636 uses and the API validates. */
function base64url(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach(byte => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Draw a verifier, keep it, and return the challenge to send with the flow.
 *
 * The server stores only the challenge. An application that intercepts the deep
 * link therefore holds a code it cannot spend, which is the entire reason the
 * custom scheme is acceptable.
 *
 * @returns The base64url SHA-256 of the verifier.
 */
export async function beginNativeSignIn(): Promise<string> {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(VERIFIER_BYTES)));
  // sessionStorage, not localStorage: the verifier is meaningful for one trip
  // to the browser and back, and nothing is served by it outliving the tab.
  sessionStorage.setItem(VERIFIER_KEY, verifier);

  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

/**
 * Read the verifier once, and forget it.
 *
 * @returns The verifier, or null when no sign-in is in flight — which is what a
 *   deep link arriving out of nowhere looks like.
 */
export function takeNativeVerifier(): string | null {
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  return verifier;
}

/**
 * Hand a URL to the system browser.
 *
 * @param url - Absolute http(s) URL, typically the provider's authorization
 *   endpoint.
 * @returns True when the shell took it; false when there is no shell to ask, so
 *   the caller can fall back to an ordinary navigation.
 */
export async function openInSystemBrowser(url: string): Promise<boolean> {
  const plugin = capacitor()?.Plugins?.LiaShell;
  if (!plugin) return false;

  try {
    await plugin.openExternal({ url });
    return true;
  } catch (error) {
    logger.error('native_open_external_failed', error as Error, { component: 'nativeShell' });
    return false;
  }
}
