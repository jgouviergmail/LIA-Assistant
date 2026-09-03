'use client';

/**
 * Editing the minutes structure (ADR-258): the ordered sections LIA fills.
 *
 * A section is a heading the reader sees, an instruction the model follows and
 * a format (prose, bullets, topics, action items). The stable key the API
 * requires is derived from the heading once and kept (`template-keys.ts`), so a
 * renamed heading does not orphan the section in already-generated minutes.
 */

import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { uniqueSectionKey } from '@/lib/meetings/template-keys';
import { SECTION_KINDS, type SectionKind, type TemplateSection } from '@/types/meetings';

/** Mirrors the API bound (`MAX_TEMPLATE_SECTIONS`). */
export const MAX_TEMPLATE_SECTIONS = 12;

interface MeetingTemplateEditorProps {
  lng: Language;
  sections: TemplateSection[];
  onChange: (next: TemplateSection[]) => void;
}

function move<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function MeetingTemplateEditor({ lng, sections, onChange }: MeetingTemplateEditorProps) {
  const { t } = useTranslation(lng);

  const update = (index: number, patch: Partial<TemplateSection>) =>
    onChange(sections.map((section, i) => (i === index ? { ...section, ...patch } : section)));

  const add = () => {
    if (sections.length >= MAX_TEMPLATE_SECTIONS) return;
    const label = t('meetings.settings.new_section_label');
    onChange([
      ...sections,
      {
        key: uniqueSectionKey(
          label,
          sections.map(s => s.key)
        ),
        label,
        instruction: '',
        kind: 'bullets',
      },
    ]);
  };

  return (
    <div className="space-y-4">
      <ol className="space-y-3">
        {sections.map((section, index) => {
          const base = `template-section-${index}`;
          return (
            <li key={section.key} className="rounded-md border border-border/60 p-3 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-muted-foreground">
                  {t('meetings.settings.section_position', { position: index + 1 })}
                </span>
                <span className="inline-flex gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t('meetings.settings.move_up', { label: section.label })}
                    aria-disabled={index === 0}
                    onClick={() => index > 0 && onChange(move(sections, index, index - 1))}
                  >
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t('meetings.settings.move_down', { label: section.label })}
                    aria-disabled={index === sections.length - 1}
                    onClick={() =>
                      index < sections.length - 1 && onChange(move(sections, index, index + 1))
                    }
                  >
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="text-destructive"
                    aria-label={t('meetings.settings.remove_section', { label: section.label })}
                    aria-disabled={sections.length <= 1}
                    onClick={() =>
                      sections.length > 1 && onChange(sections.filter((_, i) => i !== index))
                    }
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
                <div className="space-y-3">
                  <Label htmlFor={`${base}-label`}>{t('meetings.settings.section_label')}</Label>
                  <Input
                    id={`${base}-label`}
                    value={section.label}
                    maxLength={80}
                    onChange={e => update(index, { label: e.target.value })}
                  />
                </div>
                <div className="space-y-3">
                  <Label htmlFor={`${base}-kind`}>{t('meetings.settings.section_kind')}</Label>
                  <Select
                    value={section.kind}
                    onValueChange={value => update(index, { kind: value as SectionKind })}
                  >
                    <SelectTrigger id={`${base}-kind`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SECTION_KINDS.map(kind => (
                        <SelectItem key={kind} value={kind}>
                          {t(`meetings.settings.kind_${kind}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-3">
                <Label htmlFor={`${base}-instruction`}>
                  {t('meetings.settings.section_instruction')}
                </Label>
                <Textarea
                  id={`${base}-instruction`}
                  rows={2}
                  maxLength={600}
                  value={section.instruction}
                  onChange={e => update(index, { instruction: e.target.value })}
                />
              </div>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-disabled={sections.length >= MAX_TEMPLATE_SECTIONS}
          onClick={add}
        >
          <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.settings.add_section')}
        </Button>
        <span className="text-xs text-muted-foreground">
          {t('meetings.settings.max_sections', { count: MAX_TEMPLATE_SECTIONS })}
        </span>
      </div>
    </div>
  );
}
