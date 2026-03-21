'use client';

import React, { createContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import apiClient from './api-client';

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
  voice_enabled: boolean;
  voice_mode_enabled: boolean;
  tokens_display_enabled: boolean;
  debug_panel_enabled: boolean;
  sub_agents_enabled: boolean;
  onboarding_completed: boolean;
  theme?: string;
  color_theme?: string;
  font_family?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<User>;
  register: (
    email: string,
    password: string,
    name?: string,
    rememberMe?: boolean,
    timezone?: string,
    language?: string
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
        const isAuthPage = pathname.match(/^\/([a-z]{2}\/)?(login|register|oauth-callback)/);

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
  const login = async (email: string, password: string, rememberMe = false): Promise<User> => {
    try {
      const response = await apiClient.post<{ user: User }>('/auth/login', {
        email,
        password,
        remember_me: rememberMe,
      });

      setUser(response.user);
      return response.user;
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
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
    language?: string
  ): Promise<User> => {
    try {
      const response = await apiClient.post<{ user: User }>('/auth/register', {
        email,
        password,
        full_name: name,
        remember_me: rememberMe,
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
  const logout = async (): Promise<void> => {
    try {
      await apiClient.post('/auth/logout');
    } catch (error) {
      console.error('Logout error:', error);
      // Continue with logout even if API call fails
    } finally {
      setUser(null);
      router.push('/login');
    }
  };

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
      window.location.href = authorization_url;
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
  // Only user and isLoading change after mount — functions are stable or recreated
  // but don't affect consumer rendering (they're only called on user action).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const contextValue = useMemo(
    () => ({
      user,
      isLoading,
      login,
      register,
      logout,
      initiateGoogleOAuth,
      refreshUser,
    }),
    [user, isLoading]
  );

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>;
};
