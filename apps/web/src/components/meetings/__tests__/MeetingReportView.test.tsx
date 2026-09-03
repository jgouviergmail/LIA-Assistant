/**
 * The read-only minutes: every section kind renders its own shape, an empty
 * section says so instead of vanishing, participants and actions display the
 * same way the PDF and the email do.
 */

import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingReport } from '@/types/meetings';

import { MeetingReportView, actionDisplay, participantDisplay } from '../MeetingReportView';

const REPORT: MeetingReport = {
  title: 'Point projet',
  participants: [
    { label: 'S1', name: 'Claire', role: 'chef de projet' },
    { label: 'S2', name: 'Marc', role: null },
    { label: 'S3', name: null, role: null },
  ],
  sections: [
    {
      key: 'summary',
      label: 'Résumé',
      kind: 'paragraph',
      paragraph: 'Ligne 1\nLigne 2',
      bullets: [],
      topics: [],
      action_items: [],
      transcript: [],
    },
    {
      key: 'decisions',
      label: 'Décisions',
      kind: 'bullets',
      paragraph: null,
      bullets: ['Mise en production le 26', ''],
      topics: [],
      action_items: [],
      transcript: [],
    },
    {
      key: 'topics',
      label: 'Sujets',
      kind: 'topics',
      paragraph: null,
      bullets: [],
      topics: [{ title: 'Migration', summary: 'Terminée mardi.' }],
      action_items: [],
      transcript: [],
    },
    {
      key: 'action_items',
      label: 'Actions',
      kind: 'action_items',
      paragraph: null,
      bullets: [],
      topics: [],
      action_items: [
        { description: 'Préparer la bascule', owner: 'Marc', due_date: '2026-09-09' },
        { description: 'Relancer le prestataire', owner: null, due_date: null },
      ],
      transcript: [],
    },
    {
      key: 'risks',
      label: 'Risques',
      kind: 'bullets',
      paragraph: null,
      bullets: ['   '],
      topics: [],
      action_items: [],
      transcript: [],
    },
  ],
};

describe('display helpers', () => {
  it('names a participant by name then role, or by label', () => {
    expect(participantDisplay({ label: 'S1', name: 'Claire', role: 'chef de projet' })).toBe(
      'Claire (chef de projet)'
    );
    expect(participantDisplay({ label: 'S2', name: 'Marc', role: null })).toBe('Marc');
    expect(participantDisplay({ label: 'S3', name: null, role: null })).toBe('S3');
  });

  it('joins only the known fields of an action', () => {
    expect(actionDisplay({ description: 'A', owner: 'Marc', due_date: '2026-09-09' })).toBe(
      'A · Marc · 2026-09-09'
    );
    expect(actionDisplay({ description: 'B', owner: null, due_date: null })).toBe('B');
  });
});

describe('MeetingReportView', () => {
  it('renders every kind in its shape and the participants line', () => {
    renderWithProviders(<MeetingReportView lng="en" report={REPORT} />);
    expect(screen.getByText('Claire (chef de projet), Marc, S3')).toBeInTheDocument();
    expect(screen.getByText(/Ligne 1/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: 'Migration' })).toBeInTheDocument();
    expect(screen.getByText('Terminée mardi.')).toBeInTheDocument();
    expect(screen.getByText('Préparer la bascule · Marc · 2026-09-09')).toBeInTheDocument();
    expect(screen.getByText('Relancer le prestataire')).toBeInTheDocument();
    // The empty decision is not rendered as a blank bullet.
    expect(screen.getByRole('heading', { level: 3, name: 'Décisions' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem').map(li => li.textContent)).not.toContain('');
  });

  it('says a section is empty instead of hiding it', () => {
    renderWithProviders(<MeetingReportView lng="en" report={REPORT} />);
    expect(screen.getByRole('heading', { level: 3, name: 'Risques' })).toBeInTheDocument();
    expect(screen.getAllByText('meetings.detail.section_empty')).toHaveLength(1);
  });

  it('omits the participants block when nobody is listed', () => {
    renderWithProviders(<MeetingReportView lng="en" report={{ ...REPORT, participants: [] }} />);
    expect(screen.queryByText('meetings.detail.participants_title')).not.toBeInTheDocument();
  });
});

describe('MeetingReportView — transcript kind (ADR-259)', () => {
  const transcriptReport: MeetingReport = {
    title: 'Dictée',
    participants: [],
    sections: [
      {
        key: 'transcript',
        label: 'Transcription',
        kind: 'transcript',
        paragraph: null,
        bullets: [],
        topics: [],
        action_items: [],
        transcript: [
          { speaker: 'S1', start: 0, text: 'Bonjour à tous.' },
          { speaker: 'S2', start: 65, text: 'Bonjour Marie.' },
        ],
      },
      {
        key: 'empty',
        label: 'Vide',
        kind: 'transcript',
        paragraph: null,
        bullets: [],
        topics: [],
        action_items: [],
        transcript: [],
      },
    ],
  };

  it('renders one timestamped, speaker-labelled line per turn and says when empty', () => {
    renderWithProviders(<MeetingReportView lng="en" report={transcriptReport} />);
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('0:00');
    expect(items[0]).toHaveTextContent('S1');
    expect(items[0]).toHaveTextContent('Bonjour à tous.');
    expect(items[1]).toHaveTextContent('1:05');
    expect(screen.getByText('meetings.detail.section_empty')).toBeInTheDocument();
  });
});
