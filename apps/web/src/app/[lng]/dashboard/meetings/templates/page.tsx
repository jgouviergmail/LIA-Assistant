'use client';

/**
 * The minutes template library page (ADR-259, recomposed after the owner's
 * review): « My templates » and the built-ins, with batches.
 *
 * The working screen (library, preview, form, batches) is
 * `MeetingTemplateManager`, which the meetings settings section mounts too —
 * one implementation for both doors. This page adds its way back and its
 * title.
 */

import { ArrowLeft, LibraryBig } from 'lucide-react';

import { MeetingTemplateManager } from '@/components/meetings/MeetingTemplateManager';
import { Button } from '@/components/ui/button';
import { useBackOrigin } from '@/hooks/useBackOrigin';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeetingTemplates } from '@/hooks/useMeetingTemplates';
import { useTranslation } from '@/i18n/client';
import { withOrigin } from '@/lib/back-origin';

interface TemplatesPageProps {
  params: Promise<{ lng: string }>;
}

export default function TemplatesPage({ params }: TemplatesPageProps) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  // Carried forward so the list keeps the way back the reader arrived with.
  const listHref = withOrigin('/dashboard/meetings', useBackOrigin());
  const library = useMeetingTemplates();

  return (
    <div className="space-y-6">
      <div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="-ml-2"
          onClick={() => router.push(listHref)}
        >
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.back')}
        </Button>
      </div>

      <header>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <LibraryBig className="h-6 w-6 text-primary" aria-hidden="true" />
          {t('meetings.templates.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('meetings.templates.subtitle')}</p>
      </header>

      <MeetingTemplateManager lng={lng} library={library} />
    </div>
  );
}
