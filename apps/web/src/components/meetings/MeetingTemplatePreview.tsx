'use client';

/**
 * A template read-only (ADR-259): what a reader checks before adding a
 * built-in to their own — the sections in order, each with its heading,
 * format and the instruction LIA follows. Nothing here is editable; a
 * built-in is added to « My templates » and edited there.
 */

import { ArrowLeft, FolderPlus } from 'lucide-react';

import { TemplateCategoryGlyph } from '@/components/meetings/templateCategoryIcons';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isTranscriptTemplate } from '@/lib/meetings/templates';
import type { MeetingTemplate } from '@/types/meetings';

export interface MeetingTemplatePreviewProps {
  lng: Language;
  template: MeetingTemplate;
  onBack: () => void;
  /** « Add to my templates » — offered for a built-in only. */
  onAddToMine?: () => void;
  /** The cap is reached: adding is refused, the caller explains why. */
  addBlocked?: boolean;
}

export function MeetingTemplatePreview({
  lng,
  template,
  onBack,
  onAddToMine,
  addBlocked = false,
}: MeetingTemplatePreviewProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.templates.back_to_library')}
        </Button>
        {onAddToMine && (
          <Button
            type="button"
            size="sm"
            aria-disabled={addBlocked || undefined}
            onClick={onAddToMine}
          >
            <FolderPlus className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.templates.add_to_mine')}
          </Button>
        )}
      </div>

      <header className="space-y-2">
        <h2 className="flex items-center gap-2 text-xl font-semibold text-primary">
          <TemplateCategoryGlyph category={template.category} className="h-5 w-5 shrink-0" />
          {template.name}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="default" size="sm">
            {t(`meetings.templates.category.${template.category}`)}
          </Badge>
          <Badge variant="default" size="sm">
            {t('meetings.templates.sections_count', { count: template.sections.length })}
          </Badge>
          {template.builtin && (
            <Badge variant="outline" size="sm">
              {t('meetings.templates.builtin_badge')}
            </Badge>
          )}
          {isTranscriptTemplate(template) && (
            <Badge variant="warning" size="sm">
              {t('meetings.templates.transcript_badge')}
            </Badge>
          )}
        </div>
        {template.description && (
          <p className="text-sm text-muted-foreground">{template.description}</p>
        )}
      </header>

      <ol className="space-y-3">
        {template.sections.map((section, index) => (
          <li key={section.key} className="rounded-lg border bg-card/60 p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t('meetings.settings.section_position', { position: index + 1 })}
              </span>
              <span className="font-semibold text-primary">{section.label}</span>
              <Badge variant="outline" size="sm">
                {t(`meetings.settings.kind_${section.kind}`)}
              </Badge>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm">{section.instruction}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
