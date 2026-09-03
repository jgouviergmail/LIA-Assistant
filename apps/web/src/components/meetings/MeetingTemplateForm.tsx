'use client';

/**
 * Creating or editing a user template (ADR-259): a name, an optional
 * description, a category, and the sections through the shared editor.
 *
 * Validation is stated, never silent: a blank name marks the field invalid,
 * an incomplete section (no heading or no instruction) blocks the submit with
 * an alert, and a save in flight is shown on the submit itself (`isLoading`,
 * the app-wide pending-action shape) while the form announces `aria-busy`.
 */

import { useId, useState } from 'react';

import { MeetingTemplateEditor } from '@/components/meetings/MeetingTemplateEditor';
import { Button } from '@/components/ui/button';
import { FieldFrame } from '@/components/ui/field';
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
import {
  TEMPLATE_CATEGORIES,
  type MeetingTemplateUpdate,
  type TemplateCategory,
  type TemplateSection,
} from '@/types/meetings';

export interface MeetingTemplateFormProps {
  lng: Language;
  title: string;
  initial: MeetingTemplateUpdate;
  isSaving: boolean;
  onSubmit: (values: MeetingTemplateUpdate) => void;
  onCancel: () => void;
}

/** A section is complete once it has a heading and an instruction. */
function sectionsComplete(sections: readonly TemplateSection[]): boolean {
  return (
    sections.length > 0 && sections.every(s => s.label.trim() !== '' && s.instruction.trim() !== '')
  );
}

export function MeetingTemplateForm({
  lng,
  title,
  initial,
  isSaving,
  onSubmit,
  onCancel,
}: MeetingTemplateFormProps) {
  const { t } = useTranslation(lng);
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description ?? '');
  const [category, setCategory] = useState<TemplateCategory>(initial.category);
  const [sections, setSections] = useState<TemplateSection[]>(initial.sections);
  const [attempted, setAttempted] = useState(false);
  const nameId = useId();
  const descriptionId = useId();
  const categoryId = useId();
  const titleId = useId();

  const nameMissing = name.trim() === '';
  const incomplete = !sectionsComplete(sections);

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSaving) return;
    setAttempted(true);
    if (nameMissing || incomplete) return;
    onSubmit({
      name: name.trim(),
      description: description.trim() === '' ? null : description.trim(),
      category,
      sections,
    });
  };

  return (
    <form
      onSubmit={submit}
      noValidate
      className="space-y-6"
      aria-labelledby={titleId}
      aria-busy={isSaving || undefined}
    >
      <h2 id={titleId} className="text-xl font-semibold">
        {title}
      </h2>

      <FieldFrame
        label={t('meetings.templates.form.name')}
        fieldId={nameId}
        error={attempted && nameMissing ? t('meetings.templates.form.name_missing') : undefined}
        errorId={`${nameId}-error`}
      >
        <Input
          id={nameId}
          value={name}
          onChange={e => setName(e.target.value)}
          aria-invalid={attempted && nameMissing ? true : undefined}
          aria-describedby={attempted && nameMissing ? `${nameId}-error` : undefined}
          maxLength={100}
          autoComplete="off"
        />
      </FieldFrame>

      <FieldFrame
        label={t('meetings.templates.form.description')}
        fieldId={descriptionId}
        errorId={`${descriptionId}-error`}
      >
        <Textarea
          id={descriptionId}
          value={description}
          onChange={e => setDescription(e.target.value)}
          rows={2}
          maxLength={300}
        />
      </FieldFrame>

      <div className="space-y-3">
        <Label htmlFor={categoryId}>{t('meetings.templates.form.category')}</Label>
        <Select value={category} onValueChange={value => setCategory(value as TemplateCategory)}>
          <SelectTrigger id={categoryId} className="w-full sm:max-w-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEMPLATE_CATEGORIES.map(item => (
              <SelectItem key={item} value={item}>
                {t(`meetings.templates.category.${item}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <section className="space-y-3">
        <h3 className="text-base font-medium">{t('meetings.templates.form.sections_title')}</h3>
        <MeetingTemplateEditor lng={lng} sections={sections} onChange={setSections} />
        {attempted && incomplete && (
          <p role="alert" className="text-sm font-medium text-destructive">
            {t('meetings.templates.form.incomplete')}
          </p>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" isLoading={isSaving} loadingText={t('common.saving')}>
          {t('common.save')}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}
