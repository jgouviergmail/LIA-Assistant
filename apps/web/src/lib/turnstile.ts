/**
 * Cloudflare Turnstile on the password doors (ADR-364).
 *
 * The widget runs in the browser and hands back a short-lived, single-use
 * token; the API asks Cloudflare about it before a sign-up, a password sign-in
 * or a reset request goes any further. The widget alone protects nothing — a
 * script posting to the API never runs it — so the token travels in
 * {@link TURNSTILE_TOKEN_HEADER} and the server decides.
 *
 * The loader is injected on demand, only when the instance publishes a site key
 * (`GET /auth/features`), and once per page however many widgets ask. The CSP
 * allows `https://challenges.cloudflare.com` for exactly this (script + frame).
 */

/** The explicit-render loader: the application decides where and when a widget appears. */
export const TURNSTILE_SCRIPT_URL =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

/** The header the API reads the token from (`TURNSTILE_TOKEN_HEADER` server-side). */
export const TURNSTILE_TOKEN_HEADER = 'X-LIA-Turnstile-Response';

/** The door a token is produced for — checked by the API on return. */
export type TurnstileAction = 'login' | 'register' | 'password_reset';

/**
 * The doors that may submit WITHOUT a token once the widget could not load — the
 * sign-in alone, as `PROCEEDS_WHEN_UNAVAILABLE` server-side. An outage reaches the
 * browser too; the API then lets the sign-in through only while Cloudflare does
 * not answer the server either (ADR-364), and a new account or a reset e-mail waits.
 */
export const SUBMITS_WITHOUT_WIDGET: ReadonlySet<TurnstileAction> = new Set(['login']);

export interface TurnstileRenderOptions {
  sitekey: string;
  action: TurnstileAction;
  theme: 'light' | 'dark';
  language: string;
  size: 'flexible';
  appearance: 'interaction-only';
  callback: (token: string) => void;
  'expired-callback': () => void;
  'error-callback': () => boolean;
}

/** The part of Cloudflare's `window.turnstile` this application uses. */
export interface TurnstileApi {
  render: (container: HTMLElement, options: TurnstileRenderOptions) => string | undefined;
  reset: (widgetId: string) => void;
  remove: (widgetId: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;

/**
 * Load Cloudflare's script once and resolve with its API.
 *
 * A failed load removes its script and forgets the attempt, so a later widget
 * (or a reload of the page) can try again.
 *
 * @returns The Turnstile API.
 */
export function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (loading) return loading;
  loading = new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = TURNSTILE_SCRIPT_URL;
    script.async = true;
    const fail = (reason: string) => {
      loading = null;
      script.remove();
      reject(new Error(reason));
    };
    script.addEventListener('load', () => {
      if (window.turnstile) resolve(window.turnstile);
      else fail('Turnstile loaded without its API');
    });
    script.addEventListener('error', () => fail('Turnstile could not be loaded'));
    document.head.appendChild(script);
  });
  return loading;
}

/** Forget the loader's state between tests. */
export function resetTurnstileLoaderForTests(): void {
  loading = null;
}

/**
 * The language Cloudflare should speak in the widget.
 *
 * @param lng - The interface language (`zh` on the frontend).
 * @returns An ISO 639-1 code, region-qualified where the frontend code is not one.
 */
export function turnstileLanguage(lng: string): string {
  return lng === 'zh' ? 'zh-CN' : lng;
}

const ERROR_KEYS: Record<string, string> = {
  turnstile_failed: 'auth.errors.turnstile_failed',
  turnstile_unavailable: 'auth.errors.turnstile_unavailable',
};

/**
 * The i18n key for a refusal of the bot check, if the error is one.
 *
 * A refused check on a request sent WITHOUT the widget (it could not load) is
 * a check blocked in THIS browser: the API refuses such a sign-in only while
 * Cloudflare answers it, so retrying cannot help and allowing the challenge
 * host can (ADR-364).
 *
 * @param error - What the API client threw.
 * @param widgetFailed - Whether the widget could not load on this page.
 * @returns The key, or null when the error is something else.
 */
export function turnstileErrorKey(error: unknown, widgetFailed = false): string | null {
  const detail = (error as { data?: { detail?: { error?: unknown } } } | undefined)?.data?.detail;
  const code = typeof detail?.error === 'string' ? detail.error : undefined;
  if (widgetFailed && code === 'turnstile_failed') return 'auth.turnstile.blocked';
  return (code && ERROR_KEYS[code]) || null;
}

/**
 * The request config carrying a token, for `apiClient.post`.
 *
 * @param token - The widget's token, or null when there is none.
 * @returns The config with the header, or undefined.
 */
export function turnstileHeaders(token: string | null): { headers: Record<string, string> } | undefined {
  return token ? { headers: { [TURNSTILE_TOKEN_HEADER]: token } } : undefined;
}
