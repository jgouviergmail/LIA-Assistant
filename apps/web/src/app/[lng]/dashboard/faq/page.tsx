import { Metadata } from 'next';
import { FAQPageClient } from '@/components/faq/FAQPageClient';
import { ScopedTranslations } from '@/components/ScopedTranslations';
import { initI18next, validateLanguage } from '@/i18n';
import { HelpCircle } from '@/lib/icons';
import { SectionHeader } from '@/components/ui/section-header';

export const metadata: Metadata = {
  title: 'FAQ - LIA',
  description: 'Questions fréquemment posées',
};

interface FAQPageProps {
  params: Promise<{ lng: string }>;
}

export default async function FAQPage({ params }: FAQPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return (
    <div className="space-y-6">
      {/* Header */}
      <SectionHeader
        level={1}
        icon={HelpCircle}
        title={t('faq.title')}
        description={t('faq.subtitle')}
      />

      {/* FAQ Content with Welcome Button. Its text is left out of every other
          page's payload (`i18n/scoped-translations.ts`) and comes back here. */}
      <ScopedTranslations lng={lng} scopes={['faq.sections', 'faq.changelog', 'faq.intro']}>
        <FAQPageClient lng={lng} />
      </ScopedTranslations>
    </div>
  );
}
