import type { ReactNode } from 'react';

import { ScopedTranslations } from '@/components/ScopedTranslations';
import { validateLanguage } from '@/i18n';
import { DASHBOARD_TRANSLATION_SCOPES } from '@/i18n/scoped-translations';
import DashboardLayoutClient from './DashboardLayoutClient';

/** Keep the application catalogue at its server boundary, outside public pages. */
export default async function DashboardLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lng: string }>;
}) {
  const lng = validateLanguage((await params).lng);
  return (
    <ScopedTranslations lng={lng} scopes={DASHBOARD_TRANSLATION_SCOPES}>
      <DashboardLayoutClient params={params}>{children}</DashboardLayoutClient>
    </ScopedTranslations>
  );
}
