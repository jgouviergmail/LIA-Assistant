import type { ReactNode } from 'react';

import { ScopedTranslations } from '@/components/ScopedTranslations';
import { validateLanguage } from '@/i18n';
import { MORE_TRANSLATION_SCOPES } from '@/i18n/scoped-translations';

/** The animated examples alone receive their settings and personal labels. */
export default async function MoreLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lng: string }>;
}) {
  const lng = validateLanguage((await params).lng);
  return (
    <ScopedTranslations lng={lng} scopes={MORE_TRANSLATION_SCOPES}>
      {children}
    </ScopedTranslations>
  );
}
