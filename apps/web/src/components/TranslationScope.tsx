/**
 * Translation Scope
 *
 * Client half of `ScopedTranslations`: adds route-scoped subtrees to the
 * catalogue the root `TranslationsProvider` holds, for its children only.
 */

'use client';

import { useMemo, type ReactNode } from 'react';
import { I18nextProvider, initReactI18next, useTranslation } from 'react-i18next';
import { createInstance } from 'i18next';
import { defaultNS, getOptions, type Language } from '@/i18n/settings';
import {
  isTranslationTree,
  mergeTranslations,
  type TranslationTree,
} from '@/i18n/scoped-translations';

interface TranslationScopeProps {
  children: ReactNode;
  locale: Language;
  /** The subtrees to add, at their place in the catalogue. */
  translations: TranslationTree;
}

/**
 * Provides an i18n instance holding the inherited catalogue plus `translations`.
 *
 * The inherited catalogue is read from the parent instance, never sent again:
 * the point of a scope is that its payload carries only what it adds. Built
 * like `TranslationsProvider`'s (inline resources load synchronously, so the
 * first render already translates).
 *
 * @param props - Scope props.
 */
export function TranslationScope({ children, locale, translations }: TranslationScopeProps) {
  const { i18n: parent } = useTranslation();
  const scoped = useMemo(() => {
    const inherited: unknown = parent.getResourceBundle(locale, defaultNS);
    const instance = createInstance();
    void instance.use(initReactI18next).init({
      ...getOptions(locale, defaultNS),
      lng: locale,
      resources: {
        [locale]: {
          [defaultNS]: mergeTranslations(
            isTranslationTree(inherited) ? inherited : {},
            translations
          ),
        },
      },
    });
    return instance;
  }, [parent, locale, translations]);

  return <I18nextProvider i18n={scoped}>{children}</I18nextProvider>;
}
