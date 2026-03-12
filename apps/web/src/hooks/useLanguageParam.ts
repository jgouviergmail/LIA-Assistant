import { useState, useEffect } from 'react';
import { type Language, fallbackLng, languages } from '@/i18n/settings';

/**
 * Custom hook to extract and manage language parameter from Next.js async params
 *
 * This hook handles the common pattern of extracting the `lng` parameter
 * from Next.js 16+ async params Promise and managing it as local state.
 * It validates that the language is supported and falls back to default if not.
 *
 * @param params Promise containing the language parameter (string from Next.js routing)
 * @returns The current validated language code
 *
 * @example
 * ```tsx
 * interface PageProps {
 *   params: Promise<{ lng: string }>;
 * }
 *
 * export default function MyPage({ params }: PageProps) {
 *   const lng = useLanguageParam(params);
 *   const { t } = useTranslation(lng);
 *
 *   return <div>{t('hello')}</div>;
 * }
 * ```
 */
export function useLanguageParam(params: Promise<{ lng: string }>): Language {
  const [lng, setLng] = useState<Language>(fallbackLng);

  useEffect(() => {
    params.then(p => {
      const validLng = languages.includes(p.lng as Language) ? (p.lng as Language) : fallbackLng;
      setLng(validLng);
    });
  }, [params]);

  return lng;
}
