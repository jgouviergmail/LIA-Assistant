/**
 * Modern Fetch API-based HTTP client for Next.js 15.
 *
 * Replaces axios with native Fetch API for:
 * - Zero dependencies
 * - Better Next.js integration
 * - Smaller bundle size
 * - Native TypeScript support
 */

import { API_TIMEOUT_DEFAULT } from '@/lib/constants';

/**
 * HTTP client error with status code and response data.
 */
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
 * Handle fetch response and errors.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  // Handle 401 Unauthorized - redirect to login
  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      const pathname = window.location.pathname;

      // Check if on a public route (auth pages or landing page)
      // Matches: /login, /register, /oauth-callback, /, /en, /fr/
      // Also matches: /en/login, /fr/register, /es/oauth-callback, etc.
      const isPublicRoute =
        pathname.match(/^\/([a-z]{2}\/)?(login|register|oauth-callback)/) ||
        pathname.match(/^\/([a-z]{2})?\/?$/);

      if (!isPublicRoute) {
        // Extract current language from pathname (e.g., /en/dashboard → 'en')
        const langMatch = pathname.match(/^\/([a-z]{2})\//);
        const currentLang = langMatch ? langMatch[1] : null;

        // Redirect to localized login page to preserve user's language
        // e.g., /en/dashboard → /en/login, /dashboard → /login
        const loginPath = currentLang ? `/${currentLang}/login` : '/login';
        window.location.href = loginPath;
      }
    }
    throw new ApiError('Unauthorized', 401);
  }

  // Handle 403 Forbidden - check if user account is inactive
  if (response.status === 403) {
    // Try to parse response to check for specific error
    try {
      const text = await response.clone().text();
      const data = text ? JSON.parse(text) : null;

      // Check if this is a user_inactive error
      if (data?.detail === 'User account is inactive') {
        if (typeof window !== 'undefined') {
          const pathname = window.location.pathname;
          const isAccountInactivePage = pathname.match(/^\/([a-z]{2}\/)?account-inactive/);

          if (!isAccountInactivePage) {
            // Extract current language from pathname
            const langMatch = pathname.match(/^\/([a-z]{2})\//);
            const currentLang = langMatch ? langMatch[1] : null;

            // Redirect to account-inactive page
            // Note: /auth/me now returns 200 with is_active=false, so this handler
            // is only triggered by other endpoints that require active users
            const inactivePath = currentLang
              ? `/${currentLang}/account-inactive`
              : '/account-inactive';
            window.location.href = inactivePath;
          }
        }
        throw new ApiError('User account is inactive', 403, data);
      }
    } catch (e) {
      // Re-throw ApiError (intentional), only catch JSON parsing errors
      if (e instanceof ApiError) {
        throw e;
      }
      // If parsing fails, continue with normal error handling
    }
  }

  // Handle 204 No Content (empty response)
  if (response.status === 204) {
    return undefined as T;
  }

  // Parse response body
  const contentType = response.headers.get('content-type');
  const isJson = contentType?.includes('application/json');

  // Handle empty responses
  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  const data = isJson ? JSON.parse(text) : text;

  // Handle error responses
  if (!response.ok) {
    throw new ApiError(
      data?.message || data?.detail || `HTTP ${response.status}`,
      response.status,
      data
    );
  }

  return data as T;
}

/**
 * Create AbortController with timeout.
 */
function createAbortSignal(timeout: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeout);
  return controller.signal;
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
    const signal = createAbortSignal(timeout);

    // Only include Content-Type for requests with body (POST, PUT, PATCH)
    // GET/DELETE without Content-Type avoids CORS preflight for simple requests
    const needsContentType = ['POST', 'PUT', 'PATCH'].includes(method.toUpperCase());
    const headers: Record<string, string> = {
      ...(fetchConfig.headers as Record<string, string>),
    };
    if (needsContentType) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
      method,
      credentials: 'include', // BFF Pattern: Include HTTP-only cookies
      headers,
      signal,
      ...fetchConfig,
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
 * - Sessions auto-refresh on backend, no manual token refresh required
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
