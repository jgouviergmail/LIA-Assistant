import type { ReactNode } from 'react';

import { ScopedTranslations } from '@/components/ScopedTranslations';
import { validateLanguage } from '@/i18n';

/**
 * Demo interaction labels are not part of the shared public catalogue, nor
 * are the two product demonstrations it replays from the home page.
 */
export default async function DemoLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lng: string }>;
}) {
  const lng = validateLanguage((await params).lng);
  return (
    <ScopedTranslations
      lng={lng}
      scopes={['showroom', 'execution', 'landing.home_product_demo', 'landing.product_demo']}
    >
      {children}
    </ScopedTranslations>
  );
}
