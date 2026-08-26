/**
 * Modern Fetch API-based HTTP client for Next.js 15.
 *
 * Replaces axios with native Fetch API for:
 * - Zero dependencies
 * - Better Next.js integration
 * - Smaller bundle size
 * - Native TypeScript support
 */

import { readErrorDetail } from '@/lib/api-error';
import { API_TIMEOUT_DEFAULT, NATIVE_CLIENT_HEADER } from '@/lib/constants';
import { isNativeShell } from '@/lib/native/shell';

/**
 * HTTP client error with status code and response data.
 */
/**
 * Typed 403 challenge: the endpoint demands a fresh step-up
 * re-authentication (security program D1, Lot 3). Callers wrap sensitive
 * mutations with `useStepUpGuard` to open the re-auth dialog and replay.
 */
export class ApiStepUpError extends Error {
  status: number;
  data?: unknown;

  constructor(data?: unknown) {
    super('Step-up re-authentication required');
    this.name = 'ApiStepUpError';
    this.status = 403;
    this.data = data;
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Request configuration options.
 */
export interface RequestConfig extends RequestInit {
  /** Query parameters to append to URL */
  params?: Record<string, string | number | boolean>;
  /** Request timeout in milliseconds (default: API_TIMEOUT_DEFAULT from constants) */
  timeout?: number;
}

/**
 * Determine the correct API URL based on execution context.
 *
 * Next.js 15 has two execution contexts:
 * 1. Client-side (browser): Uses relative URLs (/api) proxied by Next.js rewrites in development
 * 2. Server-side (Server Actions, SSR): Runs in Docker container, needs container name
 *
 * Development (with Next.js rewrites):
 * - Client-side: '' (empty = relative URLs like /api/v1/...)
 * - Server-side: http://localhost:8000 or http://api:8000 (Docker)
 * - Next.js proxies /api/* → http://localhost:8000/api/* via rewrites
 * - This solves cross-port cookie issues (SameSite=Lax)
 *
 * Production:
 * - Client-side: https://api.votredomaine.com (absolute URL)
 * - Server-side: http://api:8000 (Docker service name)
 * - Reverse proxy (nginx, Traefik) handles routing
 */
function getApiUrl(): string {
  // Server-side execution (Server Actions, API Routes, SSR)
  if (typeof window === 'undefined') {
    return process.env.API_URL_SERVER || 'http://api:8000';
  }

  // Client-side execution (browser)
  return process.env.NEXT_PUBLIC_API_URL || '';
}

/**
 * Get the base URL for API requests.
 */
function getBaseUrl(): string {
  const apiUrl = getApiUrl();
  const baseUrl = apiUrl ? `${apiUrl}/api/v1` : '/api/v1';

  // DEBUG: Log URL construction
  if (typeof window !== 'undefined') {
    // Removed console.log - URL construction is logged via network requests if needed
  }

  return baseUrl;
}

/**
 * Absolute URL of an API endpoint, for links the BROWSER follows directly
 * (top-level download navigations, `<a href>`). Large archives must stream
 * to disk — never fetch them into a blob. The session cookie rides along on
 * same-site top-level GETs. Regular data calls keep using the client
 * methods; a relative `/api/v1/...` href would hit the FRONTEND origin,
 * which has no such route (found live: the export download 404'd).
 */
export function apiEndpointUrl(endpoint: string): string {
  return `${getBaseUrl()}${endpoint}`;
}

/**
 * Build URL with query parameters.
 */
function buildUrl(endpoint: string, params?: Record<string, string | number | boolean>): string {
  const baseUrl = getBaseUrl();

  // Build full path by concatenating baseUrl + endpoint
  // IMPORTANT: Don't use new URL(endpoint, baseUrl) because if endpoint starts with /,
  // it will replace the baseUrl path (e.g., /api/v1) instead of appending to it
  const fullPath = `${baseUrl}${endpoint}`;

  // Handle URL construction based on whether it's absolute or relative
  if (baseUrl.startsWith('http')) {
    // Absolute URL - use URL class for proper query param handling
    const url = new URL(fullPath);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, String(value));
      });
    }
    return url.toString();
  } else {
    // Relative URL - simple string concatenation
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        searchParams.append(key, String(value));
      });
      return `${fullPath}?${searchParams.toString()}`;
    }
    return fullPath;
  }
}

/**
 * Public route segments — pages an anonymous visitor may browse.
 *
 * A 401 on these routes is expected (e.g. the AuthProvider session probe)
 * and must NOT eject the visitor to /login. Every public page under
 * `app/[lng]/` MUST be listed here: the completeness test in
 * `__tests__/api-client.public-routes.test.ts` scans the filesystem and
 * fails the build when a new public page is missing from this list —
 * the exact regression that silently ejected /why, /how, /blog and /faq
 * visitors to the login page.
 */
const PUBLIC_ROUTE_SEGMENTS = [
  'login',
  'register',
  'registration-success',
  'forgot-password',
  'reset-password',
  'verify-email',
  'oauth-callback',
  'native-auth',
  'why',
  'how',
  'story',
  'blog',
  'faq',
  'changelog',
  'more',
  'demo',
  'privacy',
  'terms',
  // PWA share-target receiver (UXR Lot 9, A6): a transient redirect page —
  // it must never be ejected to login by a stray 401 mid-redirect (the chat
  // it lands on handles authentication itself).
  'share',
] as const;

const PUBLIC_ROUTE_REGEX = new RegExp(
  `^\\/([a-z]{2}\\/)?(${PUBLIC_ROUTE_SEGMENTS.join('|')})(\\/|$)`
);

/**
 * Whether a pathname belongs to a public (anonymous-browsable) page.
 *
 * Matches with or without a locale prefix — /why, /en/blog/mcp-protocol,
 * /fr/story, /login — plus the landing root (/, /en, /fr/).
 */
export function isPublicPath(pathname: string): boolean {
  return PUBLIC_ROUTE_REGEX.test(pathname) || /^\/([a-z]{2})?\/?$/.test(pathname);
}

/** Extract the current locale segment from a pathname (e.g. /en/dashboard → 'en'). */
function currentLangFrom(pathname: string): string | null {
  const langMatch = pathname.match(/^\/([a-z]{2})\//);
  return langMatch ? langMatch[1] : null;
}

/**
 * Endpoints where a 401 means "the credentials you just submitted were
 * rejected" (wrong password/code in a step-up challenge), NOT "your session
 * expired". Their callers show an inline error — ejecting to /login would
 * destroy the flow on a simple typo.
 */
export function isCredentialCheckUrl(url: string): boolean {
  return url.includes('/auth/step-up/');
}

/** 401: eject non-public pages to the localized login, then throw. */
function handleUnauthorized(): never {
  if (typeof window !== 'undefined') {
    const pathname = window.location.pathname;
    if (!isPublicPath(pathname)) {
      const currentLang = currentLangFrom(pathname);
      // Redirect to localized login page to preserve user's language
      window.location.href = currentLang ? `/${currentLang}/login` : '/login';
    }
  }
  throw new ApiError('Unauthorized', 401);
}

/**
 * 403: throw the typed step-up challenge (D1 Lot 3) or the inactive-account
 * error (with its redirect). Unrecognized 403 bodies fall through to the
 * generic error handling.
 */
async function handleForbidden(response: Response): Promise<void> {
  try {
    const text = await response.clone().text();
    const data = text ? JSON.parse(text) : null;

    // Step-up contract: sensitive action needs re-authentication.
    if (data?.detail?.error === 'step_up_required') {
      throw new ApiStepUpError(data);
    }

    if (data?.detail === 'User account is inactive') {
      if (typeof window !== 'undefined') {
        const pathname = window.location.pathname;
        if (!pathname.match(/^\/([a-z]{2}\/)?account-inactive/)) {
          const currentLang = currentLangFrom(pathname);
          // Note: /auth/me now returns 200 with is_active=false, so this handler
          // is only triggered by other endpoints that require active users
          window.location.href = currentLang
            ? `/${currentLang}/account-inactive`
            : '/account-inactive';
        }
      }
      throw new ApiError('User account is inactive', 403, data);
    }
  } catch (e) {
    // Re-throw typed errors (intentional), only catch JSON parsing errors
    if (e instanceof ApiError || e instanceof ApiStepUpError) {
      throw e;
    }
    // If parsing fails, continue with normal error handling
  }
}

/**
 * Handle fetch response and errors.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    if (isCredentialCheckUrl(response.url)) {
      throw new ApiError('Unauthorized', 401);
    }
    handleUnauthorized();
  }

  if (response.status === 403) {
    await handleForbidden(response);
  }

  // Handle 204 No Content (empty response)
  if (response.status === 204) {
    return undefined as T;
  }

  // Parse response body
  const contentType = response.headers.get('content-type');
  const isJson = contentType?.includes('application/json');

  const text = await response.text();
  const data = text ? (isJson ? JSON.parse(text) : text) : undefined;

  // Errors are raised BEFORE the empty-body shortcut below. The other order
  // made a bare 5xx — what a load balancer answers when the upstream is down —
  // resolve with `undefined`, so the caller either read a field off nothing and
  // crashed somewhere unrelated, or displayed "no data" for an outage.
  //
  // The message goes through `readErrorDetail` rather than `data.detail`
  // directly: FastAPI answers a validation failure with a LIST of entries, and
  // handing that to `new Error(...)` stringifies it to the literal
  // "[object Object]" — which is then what the user reads on the form.
  if (!response.ok) {
    throw new ApiError(readErrorDetail(data) ?? `HTTP ${response.status}`, response.status, data);
  }

  // A successful response with no body (some 200s, every 202) is not an error.
  return data as T;
}

/**
 * Create an abort signal that fires after `timeout` ms.
 *
 * AbortSignal.timeout() owns its timer lifecycle: no timer leaks on completed
 * requests, and timeouts reject with `TimeoutError` (vs `AbortError` for
 * caller-initiated cancellation).
 */
function createAbortSignal(timeout: number): AbortSignal {
  return AbortSignal.timeout(timeout);
}

/**
 * Combine the client's timeout with a caller-supplied cancellation signal.
 *
 * Both must be able to abort the request: the timeout is the client's contract,
 * the caller's signal is how a debounced search or an unmounting component
 * stops work it no longer needs.
 *
 * @param timeoutSignal - The client's own timeout signal.
 * @param callerSignal - Whatever the caller passed in its RequestInit, if any.
 * @returns A single signal that fires when either does.
 */
function combineSignals(
  timeoutSignal: AbortSignal,
  callerSignal: AbortSignal | null | undefined
): AbortSignal {
  return callerSignal ? AbortSignal.any([timeoutSignal, callerSignal]) : timeoutSignal;
}

/**
 * Modern HTTP client using native Fetch API.
 *
 * Features:
 * - BFF Pattern: Automatic cookie inclusion (credentials: 'include')
 * - Type-safe with generics
 * - Automatic 401 handling (redirect to login)
 * - Query parameter support
 * - Timeout support (default: 30s)
 * - Zero dependencies
 *
 * Security:
 * - HTTP-only cookies (XSS-proof)
 * - SameSite=Lax (CSRF protection)
 * - No tokens in localStorage
 */
class ApiClient {
  private defaultTimeout = API_TIMEOUT_DEFAULT;

  /**
   * Perform HTTP request.
   */
  private async request<T>(
    method: string,
    endpoint: string,
    config: RequestConfig = {}
  ): Promise<T> {
    const { params, timeout = this.defaultTimeout, ...fetchConfig } = config;

    const url = buildUrl(endpoint, params);
    // The timeout and the caller's own cancellation are COMBINED, not ranked:
    // keeping only the timeout would make a debounced search unable to cancel
    // its in-flight request, and keeping only the caller's would silently drop
    // the timeout every consumer relies on.
    const signal = combineSignals(createAbortSignal(timeout), fetchConfig.signal);

    // Only include Content-Type for requests with body (POST, PUT, PATCH)
    // GET/DELETE without Content-Type avoids CORS preflight for simple requests
    const needsContentType = ['POST', 'PUT', 'PATCH'].includes(method.toUpperCase());
    const headers: Record<string, string> = {
      ...(fetchConfig.headers as Record<string, string>),
    };
    if (needsContentType) {
      headers['Content-Type'] = 'application/json';
    }

    /*
     * A native shell says so, on every request (ADR-246). An OAuth flow started
     * in the app must come back to the app, and the callback learns that from
     * the state the authorize call wrote — so the fact has to travel on an
     * ordinary API request.
     *
     * Sent unconditionally rather than on a list of OAuth paths: such a list
     * would be one more place to remember when a connector is added, and
     * forgetting it strands that connector's users in a browser, silently.
     *
     * A browser sends nothing here and pays nothing. A shell pays one CORS
     * preflight per method and path every ten minutes (the API's `max_age`).
     */
    if (isNativeShell()) {
      headers[NATIVE_CLIENT_HEADER] = '1';
    }

    // `fetchConfig` is spread FIRST on purpose. Spread last, a caller-supplied
    // `headers` would replace the object built just above (dropping the
    // computed Content-Type), a caller-supplied `signal` would drop the
    // timeout, and a caller-supplied `credentials` would break the BFF cookie
    // invariant — silently, since the merge above would still look right.
    const response = await fetch(url, {
      ...fetchConfig,
      method,
      credentials: 'include', // BFF Pattern: Include HTTP-only cookies
      headers,
      signal,
    });

    return handleResponse<T>(response);
  }

  /**
   * GET request.
   */
  async get<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.request<T>('GET', endpoint, config);
  }

  /**
   * POST request.
   */
  async post<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>('POST', endpoint, {
      ...config,
      body: JSON.stringify(data),
    });
  }

  /**
   * PUT request.
   */
  async put<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>('PUT', endpoint, {
      ...config,
      body: JSON.stringify(data),
    });
  }

  /**
   * PATCH request.
   */
  async patch<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>('PATCH', endpoint, {
      ...config,
      body: JSON.stringify(data),
    });
  }

  /**
   * DELETE request.
   */
  async delete<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.request<T>('DELETE', endpoint, config);
  }
}

/**
 * API Client singleton configured for BFF (Backend for Frontend) Pattern.
 *
 * Key features:
 * - credentials: 'include' - Automatically includes HTTP-only cookies
 * - No token management in localStorage (security improvement)
 * - No Authorization headers needed (authentication via cookies)
 * - Fixed-lifetime sessions (7d / 30d remember-me); expiry surfaces as a 401
 *   handled below — no client-side token refresh machinery
 * - Dual URL support: Client-side uses relative URLs (proxied), Server-side uses Docker service name
 *
 * Security benefits:
 * - Immune to XSS attacks (tokens never in JavaScript)
 * - HTTP-only cookies prevent client-side access
 * - SameSite=Lax prevents CSRF attacks
 * - Sessions stored server-side in Redis
 *
 * Development mode:
 * - Client-side: Relative URLs (/api/v1/...) proxied by Next.js rewrites
 * - Server-side: http://localhost:8000 or http://api:8000 (Docker)
 * - This solves cross-port cookie issues with SameSite=Lax
 *
 * Production mode:
 * - Client-side: Absolute API URL (e.g., https://api.votredomaine.com)
 * - Server-side: Docker service name (api:8000)
 * - Reverse proxy (nginx, Traefik) handles routing
 *
 * @example
 * ```ts
 * import { apiClient } from '@/lib/api-client';
 *
 * // GET request
 * const user = await apiClient.get<User>('/users/me');
 *
 * // POST request
 * const created = await apiClient.post<User>('/users', {
 *   email: 'user@example.com',
 *   password: 'password123',
 * });
 *
 * // With query parameters
 * const users = await apiClient.get<User[]>('/users', {
 *   params: { page: 1, limit: 10 }
 * });
 * ```
 */
export const apiClient = new ApiClient();

export default apiClient;
