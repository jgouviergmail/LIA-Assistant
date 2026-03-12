/**
 * Design System - Card Variants
 *
 * Visual documentation for the unified card system.
 * Accessible via /fr/dashboard/design-system/cards or /en/dashboard/design-system/cards
 *
 * Protected by dashboard authentication.
 */
import { Metadata } from 'next';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/card';
import { DOMAIN_ACCENTS } from '@/constants/card';
import { initI18next, validateLanguage } from '@/i18n';

export const metadata: Metadata = {
  title: 'Design System - Cards',
  description: 'Visual documentation for the unified card system',
};

interface CardDesignSystemPageProps {
  params: Promise<{ lng: string }>;
}

const VISUAL_VARIANTS = ['default', 'elevated', 'interactive', 'flat', 'gradient'] as const;
const STATUS_VARIANTS = ['info', 'success', 'warning', 'error'] as const;
const SIZE_VARIANTS = ['none', 'sm', 'md', 'lg'] as const;

export default async function CardDesignSystemPage({ params }: CardDesignSystemPageProps) {
  const { lng: lngParam } = await params;
  const lng = validateLanguage(lngParam);
  const { t } = await initI18next(lng);

  return (
    <div className="container mx-auto py-8 space-y-12">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">{t('designSystem.cards.title')}</h1>
        <p className="text-muted-foreground">{t('designSystem.cards.subtitle')}</p>
      </div>

      {/* Visual Variants */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.visualVariants.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('designSystem.cards.visualVariants.description')}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {VISUAL_VARIANTS.map((variant) => (
            <Card key={variant} variant={variant} size="md">
              <CardContent className="pt-4">
                <div className="font-medium">variant=&quot;{variant}&quot;</div>
                <p className="text-sm text-muted-foreground mt-1">
                  {t(`designSystem.cards.visualVariants.${variant}`)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Status Variants */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.statusVariants.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('designSystem.cards.statusVariants.description')}
        </p>
        <div className="space-y-3">
          {STATUS_VARIANTS.map((status) => (
            <Card key={status} status={status} size="md">
              <CardContent className="pt-4">
                <div className="font-medium">status=&quot;{status}&quot;</div>
                <p className="text-sm text-muted-foreground mt-1">
                  {t(`designSystem.cards.statusVariants.${status}`)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Size Variants */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.sizeVariants.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('designSystem.cards.sizeVariants.description')}
        </p>
        <div className="space-y-3">
          {SIZE_VARIANTS.map((size) => (
            <Card key={size} size={size} className="border-dashed">
              <div className="bg-muted/50 p-2 text-center">
                <div className="font-medium">size=&quot;{size}&quot;</div>
                <p className="text-xs text-muted-foreground">
                  {t(`designSystem.cards.sizeVariants.${size}`)}
                </p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* Domain Accents */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.domainAccents.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('designSystem.cards.domainAccents.description')}
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {DOMAIN_ACCENTS.map((domain) => (
            <Card key={domain} domainAccent={domain} size="sm">
              <CardContent className="pt-3">
                <code className="text-sm">{domain}</code>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Full Composition */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.fullComposition.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('designSystem.cards.fullComposition.description')}
        </p>
        <Card variant="elevated">
          <CardHeader>
            <CardTitle>{t('designSystem.cards.fullComposition.exampleTitle')}</CardTitle>
            <CardDescription>
              {t('designSystem.cards.fullComposition.exampleDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p>{t('designSystem.cards.fullComposition.exampleContent')}</p>
          </CardContent>
          <CardFooter className="text-sm text-muted-foreground">
            {t('designSystem.cards.fullComposition.exampleFooter')}
          </CardFooter>
        </Card>
      </section>

      {/* Combined Example */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.combinedProps.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('designSystem.cards.combinedProps.description')}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card variant="elevated" status="info" domainAccent="email">
            <CardHeader>
              <CardTitle>{t('designSystem.cards.combinedProps.emailCard')}</CardTitle>
              <CardDescription>
                variant=&quot;elevated&quot; + status=&quot;info&quot; +
                domainAccent=&quot;email&quot;
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {t('designSystem.cards.combinedProps.emailNote')}
              </p>
            </CardContent>
          </Card>

          <Card variant="interactive" status="warning" size="lg">
            <CardContent className="pt-0">
              <div className="font-medium">
                {t('designSystem.cards.combinedProps.interactiveWarning')}
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                variant=&quot;interactive&quot; + status=&quot;warning&quot; + size=&quot;lg&quot;
              </p>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Code Examples */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('designSystem.cards.usageExamples.title')}</h2>
        <Card size="md" className="bg-muted/30">
          <CardContent className="pt-4">
            <pre className="text-sm overflow-x-auto">
              {`// Basic card
<Card size="lg">Content</Card>

// With header structure
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>Content</CardContent>
</Card>

// Status + variant
<Card status="warning" variant="elevated">
  Warning message
</Card>

// Domain accent
<Card domainAccent="email" size="md">
  Email content
</Card>`}
            </pre>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
