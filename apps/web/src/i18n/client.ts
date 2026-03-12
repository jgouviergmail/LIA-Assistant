/**
 * Client-side i18n configuration
 *
 * Provides useTranslation hook and client-side i18n utilities
 * for Next.js 15 App Router client components.
 */

'use client';

import { useEffect, useState } from 'react';
import { createInstance, type i18n as I18nInstance } from 'i18next';
import resourcesToBackend from 'i18next-resources-to-backend';
import { initReactI18next, useTranslation as useTranslationOrg } from 'react-i18next';
import { getOptions, type Language } from './settings';

// Cache for client-side instances
const i18nInstances = new Map<string, I18nInstance>();

/**
 * Initialize client-side i18next instance
 *
 * @param lng - Language code
 * @param ns - Namespace
 * @returns Initialized i18n instance
 */
function initI18nextClient(lng: Language, ns?: string) {
  const cacheKey = `${lng}-${ns || 'translation'}`;

  if (i18nInstances.has(cacheKey)) {
    return i18nInstances.get(cacheKey)!;
  }

  const i18nInstance = createInstance();

  i18nInstance
    .use(initReactI18next)
    .use(
      resourcesToBackend(
        (language: string, namespace: string) =>
          import(`../../locales/${language}/${namespace}.json`)
      )
    )
    .init(getOptions(lng, ns));

  i18nInstances.set(cacheKey, i18nInstance);
  return i18nInstance;
}

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
 * @param lng - Language code
 * @param ns - Namespace (optional)
 * @param options - Additional options
 */
export function useTranslation(lng: Language, ns?: string, options?: { keyPrefix?: string }) {
  const [i18n, setI18n] = useState<I18nInstance | null>(null);

  useEffect(() => {
    const instance = initI18nextClient(lng, ns);
    setI18n(instance);
  }, [lng, ns]);

  const ret = useTranslationOrg(ns, options);

  // Override i18n instance if available
  if (i18n && ret.i18n !== i18n) {
    ret.i18n = i18n;
  }

  return ret;
}
