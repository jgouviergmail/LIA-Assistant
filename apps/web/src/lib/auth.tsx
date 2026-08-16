'use client';

import React, { createContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { clearInputDraft } from '@/hooks/useInputDraft';
import {
  purgeSensitiveClientStorage,
  purgeSensitiveClientStorageOnAccountChange,
} from '@/lib/client-storage-purge';
import apiClient from './api-client';
import { navigateToAuthorizationUrl } from '@/lib/safe-navigation';

export interface User {
  id: string;
  email: string;
  full_name?: string;
  picture_url?: string;
  timezone?: string;
  language?: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  memory_enabled: boolean;
  execution_mode: string;
  voice_enabled: boolean;
  voice_mode_enabled: boolean;
  voice_stt_mode: 'local' | 'remote';
  tokens_display_enabled: boolean;
  debug_panel_enabled: boolean;
  // ADR-083 Phase 2 cleanup: sub_agents_enabled removed (Option B).
  response_display_mode: string;
  onboarding_completed: boolean;
  onboarding_checklist?: { dismissed_at?: string; celebrated_at?: string } | null;
  theme?: string;
  color_theme?: string;
  font_family?: string;
  image_generation_enabled?: boolean;
  image_generation_default_quality?: string;
  image_generation_default_size?: string;
  image_generation_output_format?: string;
  use_last_known_location?: boolean;
  health_metrics_agents_enabled?: boolean;
  login_notifications_enabled?: boolean;
}

export interface LoginResult {
  /** The signed-in user, or null when a second factor is still required. */
  user: User | null;
  /** True when the account requires a TOTP/backup code step. */
  mfaRequired: boolean;
  /** Single-use token to present to verifyMfa (5 min TTL). */
  mfaToken: string | null;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<User>;
  register: (
    email: string,
    password: string,
    name?: string,
    rememberMe?: boolean,
    timezone?: string,
    language?: string,
    termsAccepted?: boolean
  ) => Promise<User>;
  logout: () => Promise<void>;
  initiateGoogleOAuth: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * AuthProvider using BFF (Backend for Frontend) Pattern
 *
 * Key differences from JWT-based auth:
 * - No tokens in localStorage
 * - Authentication via HTTP-only cookies
 * - Sessions managed server-side
 * - No manual token refresh needed
 *
 * Security benefits:
 * - Immune to XSS (tokens never in JavaScript)
 * - HTTP-only cookies prevent client-side access
 * - SameSite=Lax prevents CSRF
 */
export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useLocalizedRouter();

  /**
   * Check if user is authenticated on mount
   *
   * With BFF Pattern:
   * - No need to check localStorage
   * - Call /auth/me which validates session cookie
   * - Backend returns user info if session is valid
   *
   * Optimization: Skip auth check on public auth pages (login, register, oauth-callback)
   * to avoid unnecessary API calls and potential redirect loops.
   */
  useEffect(() => {
    const initAuth = async () => {
      // Skip auth check on public auth pages only
      if (typeof window !== 'undefined') {
        const pathname = window.location.pathname;
        // The trailing `(\/|$)` is load-bearing: without it the match is a
        // prefix test, so a future route merely *starting* with one of these
        // words (`/login-help`, `/register-invite`…) would silently lose its
        // session check and report an authenticated user as anonymous. No
        // current route is affected — the anchor keeps the skip list a
        // deliberate choice rather than a naming accident.
        //
        // `demo` is skipped too: the public showroom page renders no header
        // and consumes no auth state (verified 2026-08-06 — nothing under it
        // reads useAuth), so hydrating a session there is a pure network
        // call on a page meant to be shared and mirrored — and it broke the
        // showroom e2e zero-API oracle, which states the true contract.
        const isAuthPage = pathname.match(
          /^\/([a-z]{2}\/)?(login|register|oauth-callback|demo)(\/|$)/
        );

        if (isAuthPage) {
          // User is on an auth page - assume not authenticated
          setUser(null);
          setIsLoading(false);
          return;
        }
      }

      // For protected pages, check authentication status
      try {
        const response = await apiClient.get<User>('/auth/me');
        setUser(response);
      } catch {
        // No session or session expired - user not authenticated
        // The 401 handler in api-client will redirect to login
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  /**
   * SEC-035 — drop the previous account's client-side state.
   *
   * Logging out is not the only way the active account changes: a session can
   * expire and the next person signs in through the same tab, so no logout ever
   * runs while `sessionStorage` survives. Every sign-in path (password, MFA,
   * register, OAuth callback) ends up here because they all resolve an identity
   * into `user`, which makes this the one place that sees the transition.
   *
   * Ownership is compared rather than purged unconditionally: this state is
   * meant to survive navigation, and wiping it on every reload would break the
   * feature it protects.
   */
  useEffect(() => {
    if (user?.id) purgeSensitiveClientStorageOnAccountChange(user.id);
  }, [user?.id]);

  /**
   * Login with email and password
   *
   * BFF Flow:
   * 1. POST /auth/login with credentials + remember_me
   * 2. Backend validates and creates session
   * 3. Backend sets HTTP-only cookie (7 or 30 days TTL)
   * 4. Backend returns user info (no tokens)
   * 5. Frontend updates user state
   *
   * @param email - User email
   * @param password - User password
   * @param rememberMe - Extend session to 30 days instead of 7
   */
  const login = async (
    email: string,
    password: string,
    rememberMe = false
  ): Promise<LoginResult> => {
    // A4 device attestation: a device with push already granted proves
    // itself with its FCM token (suppresses the new-login alert and names
    // the session in "My devices"). Silent — resolves without any prompt
    // when permission is 'granted'; every failure just means "notify".
    let fcmToken: string | null = null;
    try {
      const { getNotificationPermission, requestNotificationPermission } =
        await import('@/lib/firebase');
      if (getNotificationPermission() === 'granted') {
        fcmToken = await requestNotificationPermission();
      }
    } catch {
      // Fail-safe toward notifying — never block the login on push plumbing.
    }

    try {
      const response = await apiClient.post<{
        user: User | null;
        mfa_required?: boolean;
        mfa_token?: string | null;
      }>('/auth/login', {
        email,
        password,
        remember_me: rememberMe,
        fcm_token: fcmToken,
      });

      // Two-step login (TOTP active): no session yet — the caller must
      // present the pending token + code to verifyMfa.
      if (response.mfa_required) {
        return { user: null, mfaRequired: true, mfaToken: response.mfa_token ?? null };
      }

      setUser(response.user);
      return { user: response.user, mfaRequired: false, mfaToken: null };
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
  };

  /**
   * Complete a two-step login: pending token + TOTP or backup code.
   * On success the backend sets the session cookie and returns the user.
   */
  const verifyMfa = async (mfaToken: string, code: string): Promise<User> => {
    const response = await apiClient.post<{ user: User }>('/auth/mfa/verify', {
      mfa_token: mfaToken,
      code,
    });
    setUser(response.user);
    return response.user;
  };

  /**
   * Register new user
   *
   * BFF Flow:
   * 1. POST /auth/register with user data + remember_me + timezone + language
   * 2. Backend creates user and session
   * 3. Backend sets HTTP-only cookie (7 or 30 days TTL)
   * 4. Backend returns user info (no tokens)
   * 5. Frontend updates user state
   *
   * @param email - User email
   * @param password - User password
   * @param name - User full name (optional)
   * @param rememberMe - Extend session to 30 days instead of 7
   * @param timezone - User's IANA timezone (optional, auto-detected if not provided)
   * @param language - User's preferred language (optional, auto-detected if not provided)
   */
  const register = async (
    email: string,
    password: string,
    name?: string,
    rememberMe = false,
    timezone?: string,
    language?: string,
    termsAccepted?: boolean
  ): Promise<User> => {
    try {
      const response = await apiClient.post<{ user: User }>('/auth/register', {
        email,
        password,
        full_name: name,
        remember_me: rememberMe,
        // Undefined outside a demonstrator: the field only exists where the
        // terms are enforced, and sending false there would be a lie.
        ...(termsAccepted ? { terms_accepted: true } : {}),
        timezone,
        language,
      });

      setUser(response.user);
      return response.user;
    } catch (error) {
      console.error('Register error:', error);
      throw error;
    }
  };

  /**
   * Logout user
   *
   * BFF Flow:
   * 1. POST /auth/logout
   * 2. Backend deletes session from Redis
   * 3. Backend clears session cookie
   * 4. Frontend clears user state
   * 5. Redirect to login page
   */
  const logout = useCallback(async (): Promise<void> => {
    // SEC-039 — revoke this device's push registration BEFORE the session dies.
    // Without it the token outlives the logout and Firebase keeps delivering
    // this account's notifications to the device: on a shared computer the next
    // person reads them on the lock screen, having never signed in as anyone.
    //
    // The ordering is the whole point. `/notifications/unregister-token`
    // requires an authenticated session, so the same call placed after
    // `/auth/logout` answers 401 and revokes nothing. Best effort: a failure
    // here must not keep someone signed in.
    try {
      // Imported dynamically, NOT at module scope: `AuthProvider` is mounted by
      // `app/[lng]/layout.tsx`, so a static import would pull the Firebase
      // messaging SDK into the first-load bundle of every page — the public
      // landing, the FAQ and the blog included, none of which ever touch
      // notifications. Logging out is a deliberate action; a chunk fetched at
      // that moment costs nothing anyone perceives.
      const { getExistingFcmToken } = await import('@/lib/firebase');
      const fcmToken = await getExistingFcmToken();
      if (fcmToken) {
        await apiClient.post('/notifications/unregister-token', { token: fcmToken });
      }
    } catch (error) {
      console.error('Failed to revoke the push token on logout:', error);
    }

    try {
      await apiClient.post('/auth/logout');
    } catch (error) {
      console.error('Logout error:', error);
      // Continue with logout even if API call fails
    } finally {
      // UXR Lot 2 (A7): purge the persisted chat draft — a shared computer
      // must not leak one account's draft to the next session.
      if (user?.id) clearInputDraft(user.id);
      // SEC-035: same reasoning for the client state stored under GLOBAL keys,
      // which cannot be attributed to a user once written (debug metrics
      // history carries the request text and execution details).
      purgeSensitiveClientStorage();
      setUser(null);
      router.push('/login');
    }
  }, [router, user?.id]);

  /**
   * Initiate Google OAuth flow
   *
   * BFF Flow:
   * 1. GET /auth/google/login
   * 2. Backend generates OAuth URL with state token and PKCE
   * 3. Frontend redirects user to Google
   * 4. Google redirects to /auth/google/callback (backend)
   * 5. Backend handles callback, creates session, redirects to /dashboard
   */
  const initiateGoogleOAuth = async (): Promise<void> => {
    try {
      // Fetch API returns data directly (no .data property like axios)
      const response = await apiClient.get<{ authorization_url: string }>('/auth/google/login');
      const { authorization_url } = response;

      // Redirect to Google OAuth
      navigateToAuthorizationUrl(authorization_url, 'google-login');
    } catch (error) {
      console.error('Failed to initiate Google OAuth:', error);
      throw error;
    }
  };

  /**
   * Refresh user data from backend
   *
   * Useful after updating user profile (timezone, name, etc.)
   * to sync the local state with the backend.
   */
  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const response = await apiClient.get<User>('/auth/me');
      // Only update if user data actually changed (prevents unnecessary re-renders)
      setUser(prev => {
        if (prev && JSON.stringify(prev) === JSON.stringify(response)) {
          return prev; // Same reference → no re-render
        }
        return response;
      });
    } catch (error) {
      console.error('Failed to refresh user:', error);
      // Don't throw - just log the error
    }
  }, []);

  // Memoize context value to prevent unnecessary re-renders of consumers.
  // logout and refreshUser are useCallback-wrapped (stable references).
  // login, register, initiateGoogleOAuth are recreated per render but only
  // called on user action — they don't trigger consumer re-renders.
  const contextValue = useMemo(
    () => ({
      user,
      isLoading,
      login,
      verifyMfa,
      register,
      logout,
      initiateGoogleOAuth,
      refreshUser,
    }),
    [user, isLoading, logout, refreshUser]
  );

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>;
};
