/**
 * useLocalizedRouter hook
 *
 * Provides a router that preserves the current language prefix when navigating.
 * Prevents infinite redirect loops when using router.push() in multilingual apps.
 *
 * This hook solves the problem where client components don't have access to the
 * [lng] parameter from Server Components. It extracts the language from the
 * current pathname and automatically prefixes all navigation calls.
 *
 * Pattern based on LanguageSelector component (components/LanguageSelector.tsx).
 *
 * @example
 * ```tsx
 * // Before (causes infinite loop on non-default languages)
 * const router = useRouter();
 * router.push('/dashboard'); // → /fr/dashboard (always defaults to French!)
 *
 * // After (preserves current language)
 * const router = useLocalizedRouter();
 * router.push('/dashboard'); // → /en/dashboard (if current lang is 'en')
 * ```
 */

'use client';

import { useRouter as useNextRouter, usePathname } from 'next/navigation';
import { useCallback, useMemo } from 'react';
import { getLanguageFromPath, localizePath } from '@/utils/i18n-path-utils';

interface LocalizedRouter {
  push: (href: string) => void;
  replace: (href: string) => void;
  back: () => void;
  forward: () => void;
  refresh: () => void;
  prefetch: (href: string) => void;
}

/**
 * Hook that provides a router with language-aware navigation.
 *
 * This is a drop-in replacement for Next.js useRouter() that automatically
 * preserves the current language prefix on all navigation calls.
 *
 * Solves the infinite redirect loop problem where:
 * 1. User on /en/login
 * 2. Component calls router.push('/dashboard')
 * 3. Middleware redirects /dashboard → /fr/dashboard (default!)
 * 4. Language mismatch detected → redirect loop
 *
 * With useLocalizedRouter:
 * 1. User on /en/login
 * 2. Component calls router.push('/dashboard')
 * 3. Hook converts to /en/dashboard ✓
 * 4. No redirect needed, language preserved
 *
 * @returns Localized router with push, replace, back, forward, refresh, prefetch
 *
 * @example
 * ```tsx
 * function LoginForm() {
 *   const router = useLocalizedRouter(); // ← Use this instead of useRouter()
 *
 *   const handleLogin = async () => {
 *     await login(email, password);
 *     router.push('/dashboard'); // ← Automatically becomes /en/dashboard
 *   };
 *
 *   return <form onSubmit={handleLogin}>...</form>;
 * }
 * ```
 */
export function useLocalizedRouter(): LocalizedRouter {
  const router = useNextRouter();
  const pathname = usePathname();

  // Memoize current language to avoid recalculation on every render
  const currentLang = useMemo(() => getLanguageFromPath(pathname), [pathname]);

  // Wrap push to add language prefix
  const push = useCallback(
    (href: string) => {
      const localizedHref = localizePath(href, currentLang);
      router.push(localizedHref);
    },
    [router, currentLang]
  );

  // Wrap replace to add language prefix
  const replace = useCallback(
    (href: string) => {
      const localizedHref = localizePath(href, currentLang);
      router.replace(localizedHref);
    },
    [router, currentLang]
  );

  // Wrap prefetch to add language prefix
  const prefetch = useCallback(
    (href: string) => {
      const localizedHref = localizePath(href, currentLang);
      router.prefetch(localizedHref);
    },
    [router, currentLang]
  );

  // Memoize the returned object to prevent infinite re-renders
  // Without this, every component using this hook would get a new router
  // object on every render, causing useEffect dependencies to trigger infinitely
  return useMemo(
    () => ({
      push,
      replace,
      prefetch,
      // Pass through methods that don't need localization
      back: router.back,
      forward: router.forward,
      refresh: router.refresh,
    }),
    [push, replace, prefetch, router.back, router.forward, router.refresh]
  );
}
