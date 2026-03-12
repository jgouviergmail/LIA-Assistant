import { Metadata } from 'next';
import { FAQPageClient } from '@/components/faq/FAQPageClient';
import { initI18next, validateLanguage } from '@/i18n';

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
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('faq.title')}</h1>
        <p className="mt-2 text-muted-foreground">{t('faq.subtitle')}</p>
      </div>

      {/* FAQ Content with Welcome Button */}
      <FAQPageClient lng={lng} />
    </div>
  );
}
