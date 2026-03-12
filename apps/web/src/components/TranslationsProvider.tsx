/**
 * Translations Provider
 *
 * Client-side provider that wraps the app with i18next context.
 * Initializes translations for the current language.
 */

'use client';

import { type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { createInstance, type Resource } from 'i18next';
import { initReactI18next } from 'react-i18next';
import { getOptions, type Language } from '@/i18n/settings';

interface TranslationsProviderProps {
  children: ReactNode;
  locale: Language;
  namespaces: string[];
  resources: Resource;
}

/**
 * Translations Provider component
 *
 * Should be used in the root layout to provide i18n context to all client components.
 *
 * @param props - Provider props
 */
export function TranslationsProvider({
  children,
  locale,
  namespaces,
  resources,
}: TranslationsProviderProps) {
  const i18n = createInstance();

  i18n.use(initReactI18next).init({
    ...getOptions(locale, namespaces[0]),
    lng: locale,
    resources,
    preload: [locale],
  });

  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}
