/**
 * Scoped Translations
 *
 * Server half: hands the client components below it the route-scoped subtrees
 * of the catalogue they read (`i18n/scoped-translations.ts`), which the root
 * layout leaves out of every other page.
 */

import { type ReactNode } from 'react';
import { translationBundle } from '@/i18n';
import {
  type ScopedTranslationRequest,
  pickTranslations,
  scopedTranslationPaths,
} from '@/i18n/scoped-translations';
import { type Language } from '@/i18n/settings';
import { TranslationScope } from './TranslationScope';

interface ScopedTranslationsProps {
  children: ReactNode;
  lng: Language;
  /** The route-scoped subtrees (or children of one) the client components below read. */
  scopes: readonly ScopedTranslationRequest[];
}

/**
 * Wrap the client components of a route that read route-scoped translations.
 *
 * @param props - The language, the subtrees to add, and the components reading them.
 */
export function ScopedTranslations({ children, lng, scopes }: ScopedTranslationsProps) {
  const translations = pickTranslations(translationBundle(lng), scopedTranslationPaths(scopes));
  return (
    <TranslationScope locale={lng} translations={translations}>
      {children}
    </TranslationScope>
  );
}
