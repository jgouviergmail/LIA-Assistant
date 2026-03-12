/**
 * Server-side i18n utilities
 *
 * Provides translation functions for Next.js Server Components.
 * Loads translations and returns useTranslation-like API.
 */

import { initI18next } from './index';
import { type Language } from './settings';

/**
 * Get translation function for server components
 *
 * Usage in Server Components:
 * ```tsx
 * import { getTranslation } from '@/i18n/server';
 *
 * export default async function Page({ params }: { params: { lng: Language } }) {
 *   const { t } = await getTranslation(params.lng);
 *   return <h1>{t('dashboard.title')}</h1>;
 * }
 * ```
 *
 * @param lng - Language code
 * @param ns - Namespace (default: 'translation')
 * @param options - Additional options
 */
export async function getTranslation(
  lng: Language,
  ns: string = 'translation',
  options: { keyPrefix?: string } = {}
) {
  const i18nextInstance = await initI18next(lng, ns);

  return {
    t: i18nextInstance.getFixedT(lng, ns, options.keyPrefix),
    i18n: i18nextInstance,
  };
}
