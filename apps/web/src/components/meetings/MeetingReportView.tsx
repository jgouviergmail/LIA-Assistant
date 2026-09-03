'use client';

/**
 * Read-only rendering of the minutes (ADR-258) — the same content the
 * Markdown/PDF/email carry, laid out for the page.
 */

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatElapsed } from '@/lib/meetings/format';
import type { ActionItem, MeetingReport, Participant, ReportSection } from '@/types/meetings';

export function participantDisplay(participant: Participant): string {
  const base = participant.name ?? participant.label;
  return participant.role ? `${base} (${participant.role})` : base;
}

export function actionDisplay(action: ActionItem): string {
  return [action.description, action.owner, action.due_date].filter(Boolean).join(' · ');
}

function isSectionEmpty(section: ReportSection): boolean {
  switch (section.kind) {
    case 'paragraph':
      return !(section.paragraph ?? '').trim();
    case 'bullets':
      return !section.bullets.some(item => item.trim());
    case 'topics':
      return section.topics.length === 0;
    case 'action_items':
      return section.action_items.length === 0;
    case 'transcript':
      return !section.transcript.some(line => line.text.trim());
  }
}

function SectionBody({ section, emptyLabel }: { section: ReportSection; emptyLabel: string }) {
  if (isSectionEmpty(section)) {
    return <p className="text-sm italic text-muted-foreground">{emptyLabel}</p>;
  }
  switch (section.kind) {
    case 'paragraph':
      return <p className="whitespace-pre-line text-sm leading-relaxed">{section.paragraph}</p>;
    case 'bullets':
      return (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {section.bullets
            .filter(item => item.trim())
            .map((item, index) => (
              <li key={`${section.key}-${index}`}>{item}</li>
            ))}
        </ul>
      );
    case 'topics':
      return (
        <div className="space-y-3">
          {section.topics.map((topic, index) => (
            <div key={`${section.key}-${index}`}>
              <h4 className="text-sm font-semibold">{topic.title}</h4>
              <p className="whitespace-pre-line text-sm leading-relaxed">{topic.summary}</p>
            </div>
          ))}
        </div>
      );
    case 'action_items':
      return (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {section.action_items.map((action, index) => (
            <li key={`${section.key}-${index}`}>{actionDisplay(action)}</li>
          ))}
        </ul>
      );
    case 'transcript':
      // The rewritten exchange, turn by turn: who spoke, when, and the text
      // (the same shape the transcript panel and the PDF use).
      return (
        <ol className="space-y-1 text-sm">
          {section.transcript.map((line, index) => (
            <li
              key={`${section.key}-${index}`}
              className="grid grid-cols-[3.5rem_minmax(3rem,auto)_1fr] gap-2"
            >
              <span className="tabular-nums text-muted-foreground">
                {formatElapsed(line.start)}
              </span>
              <span className="font-medium">{line.speaker}</span>
              <span className="whitespace-pre-line">{line.text}</span>
            </li>
          ))}
        </ol>
      );
  }
}

interface MeetingReportViewProps {
  lng: Language;
  report: MeetingReport;
}

export function MeetingReportView({ lng, report }: MeetingReportViewProps) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-6">
      {report.participants.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-semibold text-primary">
            {t('meetings.detail.participants_title')}
          </h3>
          <p className="text-sm">{report.participants.map(participantDisplay).join(', ')}</p>
        </section>
      )}
      {report.sections.map(section => (
        <section key={section.key}>
          <h3 className="mb-1 text-sm font-semibold text-primary">{section.label}</h3>
          <SectionBody section={section} emptyLabel={t('meetings.detail.section_empty')} />
        </section>
      ))}
    </div>
  );
}
