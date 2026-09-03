'use client';

/**
 * Editing the minutes (ADR-258): title, participants and every section in the
 * shape of its kind. Pure form state; the page saves and reverts.
 *
 * Bullets are edited as one item per line — the same text a reader would type
 * in a note — and folded back into the list on save. Topics and action items
 * keep their fields so the structured export (PDF, email, knowledge space)
 * stays structured.
 */

import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ActionItem, MeetingReport, ReportSection, TopicItem } from '@/types/meetings';

interface MeetingReportEditorProps {
  lng: Language;
  value: MeetingReport;
  onChange: (next: MeetingReport) => void;
}

/** Lines → bullet items (blank lines dropped). */
export function linesToBullets(text: string): string[] {
  return text
    .split('\n')
    .map(line => line.replace(/^[-•*]\s*/, '').trim())
    .filter(Boolean);
}

function replaceSection(report: MeetingReport, key: string, section: ReportSection): MeetingReport {
  return { ...report, sections: report.sections.map(s => (s.key === key ? section : s)) };
}

function SectionEditor({
  lng,
  section,
  onChange,
}: {
  lng: Language;
  section: ReportSection;
  onChange: (next: ReportSection) => void;
}) {
  const { t } = useTranslation(lng);
  const fieldId = `report-section-${section.key}`;

  switch (section.kind) {
    case 'paragraph':
      return (
        <div className="space-y-3">
          <Label htmlFor={fieldId}>{section.label}</Label>
          <Textarea
            id={fieldId}
            rows={5}
            value={section.paragraph ?? ''}
            onChange={e => onChange({ ...section, paragraph: e.target.value })}
          />
        </div>
      );
    case 'bullets':
      return (
        <div className="space-y-3">
          <Label htmlFor={fieldId}>{section.label}</Label>
          <Textarea
            id={fieldId}
            rows={Math.max(3, section.bullets.length + 1)}
            value={section.bullets.join('\n')}
            onChange={e => onChange({ ...section, bullets: e.target.value.split('\n') })}
            onBlur={e => onChange({ ...section, bullets: linesToBullets(e.target.value) })}
          />
          <p className="text-xs text-muted-foreground">{t('meetings.detail.bullets_hint')}</p>
        </div>
      );
    case 'topics':
      return (
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">{section.label}</legend>
          {section.topics.map((topic, index) => (
            <TopicRow
              key={`${section.key}-${index}`}
              lng={lng}
              topic={topic}
              index={index}
              onChange={next =>
                onChange({
                  ...section,
                  topics: section.topics.map((item, i) => (i === index ? next : item)),
                })
              }
              onRemove={() =>
                onChange({ ...section, topics: section.topics.filter((_, i) => i !== index) })
              }
            />
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              onChange({ ...section, topics: [...section.topics, { title: '', summary: '' }] })
            }
          >
            <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.detail.add_item')}
          </Button>
        </fieldset>
      );
    case 'action_items':
      return (
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">{section.label}</legend>
          {section.action_items.map((action, index) => (
            <ActionRow
              key={`${section.key}-${index}`}
              lng={lng}
              action={action}
              index={index}
              onChange={next =>
                onChange({
                  ...section,
                  action_items: section.action_items.map((item, i) => (i === index ? next : item)),
                })
              }
              onRemove={() =>
                onChange({
                  ...section,
                  action_items: section.action_items.filter((_, i) => i !== index),
                })
              }
            />
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              onChange({
                ...section,
                action_items: [
                  ...section.action_items,
                  { description: '', owner: null, due_date: null },
                ],
              })
            }
          >
            <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.detail.add_item')}
          </Button>
        </fieldset>
      );
  }
}

function TopicRow({
  lng,
  topic,
  index,
  onChange,
  onRemove,
}: {
  lng: Language;
  topic: TopicItem;
  index: number;
  onChange: (next: TopicItem) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation(lng);
  const base = `topic-${index}`;
  return (
    <div className="rounded-md border border-border/60 p-3 space-y-3">
      <div className="space-y-3">
        <Label htmlFor={`${base}-title`}>{t('meetings.detail.topic_title')}</Label>
        <Input
          id={`${base}-title`}
          value={topic.title}
          onChange={e => onChange({ ...topic, title: e.target.value })}
        />
      </div>
      <div className="space-y-3">
        <Label htmlFor={`${base}-summary`}>{t('meetings.detail.topic_summary')}</Label>
        <Textarea
          id={`${base}-summary`}
          rows={3}
          value={topic.summary}
          onChange={e => onChange({ ...topic, summary: e.target.value })}
        />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-destructive"
        onClick={onRemove}
      >
        <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.detail.remove_item')}
      </Button>
    </div>
  );
}

function ActionRow({
  lng,
  action,
  index,
  onChange,
  onRemove,
}: {
  lng: Language;
  action: ActionItem;
  index: number;
  onChange: (next: ActionItem) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation(lng);
  const base = `action-${index}`;
  return (
    <div className="rounded-md border border-border/60 p-3 space-y-3">
      <div className="space-y-3">
        <Label htmlFor={`${base}-description`}>{t('meetings.detail.action_description')}</Label>
        <Input
          id={`${base}-description`}
          value={action.description}
          onChange={e => onChange({ ...action, description: e.target.value })}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-3">
          <Label htmlFor={`${base}-owner`}>{t('meetings.detail.action_owner')}</Label>
          <Input
            id={`${base}-owner`}
            value={action.owner ?? ''}
            onChange={e => onChange({ ...action, owner: e.target.value || null })}
          />
        </div>
        <div className="space-y-3">
          <Label htmlFor={`${base}-due`}>{t('meetings.detail.action_due')}</Label>
          <Input
            id={`${base}-due`}
            type="date"
            value={action.due_date ?? ''}
            onChange={e => onChange({ ...action, due_date: e.target.value || null })}
          />
        </div>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-destructive"
        onClick={onRemove}
      >
        <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.detail.remove_item')}
      </Button>
    </div>
  );
}

export function MeetingReportEditor({ lng, value, onChange }: MeetingReportEditorProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Label htmlFor="report-title">{t('meetings.detail.title_label')}</Label>
        <Input
          id="report-title"
          value={value.title}
          maxLength={200}
          onChange={e => onChange({ ...value, title: e.target.value })}
        />
      </div>
      {value.participants.length > 0 && (
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">{t('meetings.detail.participants_title')}</legend>
          {value.participants.map((participant, index) => (
            <div
              key={participant.label}
              className="grid gap-3 sm:grid-cols-[6rem_1fr_1fr] sm:items-end"
            >
              <span className="text-sm text-muted-foreground">{participant.label}</span>
              <div className="space-y-3">
                <Label htmlFor={`participant-${index}-name`}>
                  {t('meetings.detail.participant_name')}
                </Label>
                <Input
                  id={`participant-${index}-name`}
                  value={participant.name ?? ''}
                  onChange={e =>
                    onChange({
                      ...value,
                      participants: value.participants.map((p, i) =>
                        i === index ? { ...p, name: e.target.value || null } : p
                      ),
                    })
                  }
                />
              </div>
              <div className="space-y-3">
                <Label htmlFor={`participant-${index}-role`}>
                  {t('meetings.detail.participant_role')}
                </Label>
                <Input
                  id={`participant-${index}-role`}
                  value={participant.role ?? ''}
                  onChange={e =>
                    onChange({
                      ...value,
                      participants: value.participants.map((p, i) =>
                        i === index ? { ...p, role: e.target.value || null } : p
                      ),
                    })
                  }
                />
              </div>
            </div>
          ))}
        </fieldset>
      )}
      {value.sections.map(section => (
        <SectionEditor
          key={section.key}
          lng={lng}
          section={section}
          onChange={next => onChange(replaceSection(value, section.key, next))}
        />
      ))}
    </div>
  );
}
