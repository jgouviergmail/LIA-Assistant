import type { ReactNode } from 'react';

import { ScopedTranslations } from '@/components/ScopedTranslations';
import { validateLanguage } from '@/i18n';
import { DASHBOARD_TRANSLATION_SCOPES } from '@/i18n/scoped-translations';

/** Development proofs mount application controls without the dashboard shell. */
export default async function WorldPreviewLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lng: string }>;
}) {
  const lng = validateLanguage((await params).lng);
  return (
    <ScopedTranslations lng={lng} scopes={DASHBOARD_TRANSLATION_SCOPES}>
      {children}
    </ScopedTranslations>
  );
}
