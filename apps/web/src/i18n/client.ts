/**
 * Client-side i18n configuration
 *
 * Reads the nearest server-supplied translation scope in client components.
 */

'use client';

import { useTranslation as useTranslationOrg } from 'react-i18next';
import type { Language } from './settings';

/**
 * useTranslation hook for client components
 *
 * Usage:
 * ```tsx
 * 'use client';
 *
 * export function MyComponent() {
 *   const { t } = useTranslation('fr', 'translation');
 *   return <h1>{t('dashboard.title')}</h1>;
 * }
 * ```
 *
 * @param _lng - Caller language hint, retained for compatibility. The nearest
 *   server-supplied provider owns the route language, including before hydration.
 * @param ns - Namespace (optional)
 * @param options - Additional options
 */
export function useTranslation(_lng: Language, ns?: string, options?: { keyPrefix?: string }) {
  // `t` and `i18n` must name the SAME scoped instance. Creating another one
  // here used to download the complete locale after hydration even though
  // `t` still read the provider. The layout/scope already owns these resources.
  // `useLanguageParam` can still report its initial fallback before its effect
  // runs; it must not override the already-correct server provider's language.
  return useTranslationOrg(ns, options);
}
