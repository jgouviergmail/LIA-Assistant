import { cookies } from 'next/headers';

import { SERVER_ACTION_TIMEOUT } from '@/lib/constants';

/**
 * Server-side API Client for Next.js Server Actions
 *
 * This module provides a dedicated API client for server-side execution contexts
 * (Server Actions, Route Handlers) that properly forwards authentication cookies
 * to the backend API using native Fetch API.
 *
 * Architecture Context:
 * - Frontend (Next.js) and Backend (FastAPI) use BFF pattern with HTTP-only cookies
 * - Client-side requests automatically include cookies via `credentials: 'include'`
 * - Server Actions run in isolated Node.js context without automatic cookie access
 * - This client bridges that gap by manually forwarding cookies from Next.js headers
 *
 * Security:
 * - Maintains HTTP-only cookie security (cookies never exposed to client JavaScript)
 * - Properly forwards session cookies for backend authentication
 * - Uses Docker service name for container-to-container communication
 *
 * @module api-server
 */

/**
 * Error class for server API errors
 */
export class ServerApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ServerApiError';
  }
}

/**
 * Request configuration options
 */
interface RequestConfig extends RequestInit {
  params?: Record<string, string | number | boolean>;
  timeout?: number;
}

/**
 * API Client for server-side requests (Server Actions, Route Handlers)
 *
 * This class must be instantiated within a Server Action or Route Handler context
 * where `cookies()` from 'next/headers' is available.
 *
 * Authentication Flow:
 * 1. Retrieves session cookie from Next.js request headers
 * 2. Forwards cookie in `Cookie` header to backend API
 * 3. Backend validates session and authenticates request
 *
 * @example
 * ```typescript
 * // In a Server Action
 * 'use server'
 *
 * export async function updateUser(userId: string, data: UserData) {
 *   const apiServer = await createServerApiClient();
 *   const response = await apiServer.patch<User>(`/users/${userId}`, data);
 *   return response;
 * }
 * ```
 */
class ServerApiClient {
  private baseURL: string;
  private sessionCookie: string | undefined;
  private isDevelopment: boolean;

  private constructor(baseURL: string, sessionCookie?: string) {
    this.baseURL = baseURL;
    this.sessionCookie = sessionCookie;
    this.isDevelopment = process.env.NODE_ENV === 'development';
  }

  /**
   * Create a new ServerApiClient instance
   */
  static async create(): Promise<ServerApiClient> {
    // Get Next.js cookies store (only available in Server Actions/Route Handlers)
    const cookieStore = await cookies();

    // Retrieve session cookie (name must match backend configuration)
    const sessionCookie = cookieStore.get('lia_session');

    // Docker service name for container-to-container communication
    const API_URL_SERVER = process.env.API_URL_SERVER || 'http://api:8000';
    const baseURL = `${API_URL_SERVER}/api/v1`;

    return new ServerApiClient(baseURL, sessionCookie?.value);
  }

  /**
   * Perform HTTP request
   */
  private async request<T>(
    method: string,
    endpoint: string,
    config: RequestConfig = {}
  ): Promise<T> {
    const { params, timeout = SERVER_ACTION_TIMEOUT, ...fetchConfig } = config;

    // Build URL with query parameters
    let url = `${this.baseURL}${endpoint}`;
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        searchParams.append(key, String(value));
      });
      url = `${url}?${searchParams.toString()}`;
    }

    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      // Debug logging in development
      if (this.isDevelopment) {
        console.log('[API Server] Request:', {
          method,
          url,
          hasCookie: !!this.sessionCookie,
        });
      }

      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          // Forward session cookie if present
          ...(this.sessionCookie && {
            Cookie: `lia_session=${this.sessionCookie}`,
          }),
          ...fetchConfig.headers,
        },
        signal: controller.signal,
        ...fetchConfig,
      });

      clearTimeout(timeoutId);

      // Handle 204 No Content (empty response)
      if (response.status === 204) {
        return undefined as T;
      }

      // Parse response
      const contentType = response.headers.get('content-type');
      const isJson = contentType?.includes('application/json');

      // Handle empty responses
      const text = await response.text();
      if (!text) {
        return undefined as T;
      }

      const data = isJson ? JSON.parse(text) : text;

      // Handle errors
      if (!response.ok) {
        const errorMessage = data?.message || data?.detail || `HTTP ${response.status}`;

        // Log errors in development, critical errors in production
        if (this.isDevelopment) {
          console.error('[API Server] Response error:', {
            status: response.status,
            url,
            message: errorMessage,
            detail: data?.detail,
          });
        } else if (response.status >= 500 || [401, 403].includes(response.status)) {
          console.error('[API Server] Critical error:', {
            status: response.status,
            url,
            message: errorMessage,
          });
        }

        throw new ServerApiError(errorMessage, response.status, data);
      }

      // Debug logging in development
      if (this.isDevelopment) {
        console.log('[API Server] Response:', {
          status: response.status,
          url,
        });
      }

      return data as T;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof ServerApiError) {
        throw error;
      }

      // Handle fetch errors (network, timeout, etc.)
      throw new ServerApiError((error as Error).message || 'Request failed', 0, error);
    }
  }

  /**
   * GET request
   */
  async get<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.request<T>('GET', endpoint, config);
  }

  /**
   * POST request
   */
  async post<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>('POST', endpoint, {
      ...config,
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * PUT request
   */
  async put<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>('PUT', endpoint, {
      ...config,
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * PATCH request
   */
  async patch<T>(endpoint: string, data?: unknown, config?: RequestConfig): Promise<T> {
    return this.request<T>('PATCH', endpoint, {
      ...config,
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * DELETE request
   */
  async delete<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.request<T>('DELETE', endpoint, config);
  }
}

/**
 * Create an authenticated API client for server-side calls
 *
 * This function must be called within a Server Action or Route Handler context
 * where `cookies()` from 'next/headers' is available.
 *
 * @returns {Promise<ServerApiClient>} Configured API client with authentication
 */
export async function createServerApiClient(): Promise<ServerApiClient> {
  return ServerApiClient.create();
}

/**
 * Type guard to check if code is running in server context
 *
 * @returns {boolean} True if running in server context (typeof window === 'undefined')
 */
export function isServerContext(): boolean {
  return typeof window === 'undefined';
}

/**
 * Get the appropriate API URL based on execution context
 *
 * @returns {string} Server API URL for server context, client URL for browser context
 */
export function getApiUrl(): string {
  if (isServerContext()) {
    return process.env.API_URL_SERVER || 'http://api:8000';
  }
  return process.env.NEXT_PUBLIC_API_URL || '';
}
