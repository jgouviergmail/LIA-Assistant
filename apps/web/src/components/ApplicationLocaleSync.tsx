/** Persist the language of a mounted application route, never a speculative fetch. */

'use client';

import { useLayoutEffect } from 'react';
import { usePathname } from 'next/navigation';
import { setLocaleCookie, type Language } from '@/i18n/settings';
import { isPublicContentPath } from '@/lib/public-pages';

/** The server-resolved locale avoids the initial fallback of useLanguageParam. */
export function ApplicationLocaleSync({ locale }: { locale: Language }) {
  const pathname = usePathname();

  useLayoutEffect(() => {
    if (!isPublicContentPath(pathname)) setLocaleCookie(locale);
  }, [pathname, locale]);

  return null;
}
