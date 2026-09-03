/**
 * Editing the minutes keeps them structured: bullets fold back from lines,
 * topics and actions keep their fields, participants can be named.
 */

import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingReport } from '@/types/meetings';

import { MeetingReportEditor, linesToBullets } from '../MeetingReportEditor';

function report(): MeetingReport {
  return {
    title: 'Point projet',
    participants: [{ label: 'S1', name: null, role: null }],
    sections: [
      {
        key: 'summary',
        label: 'Résumé',
        kind: 'paragraph',
        paragraph: 'Ok.',
        bullets: [],
        topics: [],
        action_items: [],
      },
      {
        key: 'decisions',
        label: 'Décisions',
        kind: 'bullets',
        paragraph: null,
        bullets: ['Go'],
        topics: [],
        action_items: [],
      },
      {
        key: 'topics',
        label: 'Sujets',
        kind: 'topics',
        paragraph: null,
        bullets: [],
        topics: [{ title: 'Budget', summary: 'Validé.' }],
        action_items: [],
      },
      {
        key: 'actions',
        label: 'Actions',
        kind: 'action_items',
        paragraph: null,
        bullets: [],
        topics: [],
        action_items: [{ description: 'Relancer', owner: null, due_date: null }],
      },
    ],
  };
}

describe('linesToBullets', () => {
  it('drops blank lines and leading bullet glyphs', () => {
    expect(linesToBullets('- Un\n\n• Deux \n*Trois\n   ')).toEqual(['Un', 'Deux', 'Trois']);
  });
});

/** The editor is controlled by the page: this harness plays the page. */
function Harness({
  onChange,
  initial,
}: {
  onChange: (r: MeetingReport) => void;
  initial: MeetingReport;
}) {
  const [value, setValue] = useState(initial);
  return (
    <MeetingReportEditor
      lng="en"
      value={value}
      onChange={next => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe('MeetingReportEditor', () => {
  it('edits the title and names a participant', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(<Harness onChange={onChange} initial={report()} />);
    await user.type(screen.getByLabelText('meetings.detail.title_label'), '!');
    expect((onChange.mock.calls.at(-1)?.[0] as MeetingReport).title).toBe('Point projet!');
    await user.type(screen.getByLabelText('meetings.detail.participant_name'), 'M');
    expect((onChange.mock.calls.at(-1)?.[0] as MeetingReport).participants[0].name).toBe('M');
  });

  it('folds bullet lines back into items on blur', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(<Harness onChange={onChange} initial={report()} />);
    const bullets = screen.getByLabelText('Décisions');
    await user.clear(bullets);
    await user.type(bullets, '- A{enter}{enter}B');
    await user.tab();
    const last = onChange.mock.calls.at(-1)?.[0] as MeetingReport;
    expect(last.sections[1].bullets).toEqual(['A', 'B']);
  });

  it('adds a topic and removes an action while keeping the other fields', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(<Harness onChange={onChange} initial={report()} />);
    const [addTopic] = screen.getAllByRole('button', { name: /meetings\.detail\.add_item/ });
    await user.click(addTopic);
    let last = onChange.mock.calls.at(-1)?.[0] as MeetingReport;
    expect(last.sections[2].topics).toHaveLength(2);
    expect(last.sections[2].topics[1]).toEqual({ title: '', summary: '' });

    const removeButtons = screen.getAllByRole('button', { name: /meetings\.detail\.remove_item/ });
    await user.click(removeButtons.at(-1)!);
    last = onChange.mock.calls.at(-1)?.[0] as MeetingReport;
    expect(last.sections[3].action_items).toEqual([]);
    expect(last.sections[0].paragraph).toBe('Ok.');
  });

  it('sets an action due date as an absolute date', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(<Harness onChange={onChange} initial={report()} />);
    const due = screen.getByLabelText('meetings.detail.action_due');
    await user.type(due, '2026-09-05');
    const last = onChange.mock.calls.at(-1)?.[0] as MeetingReport;
    expect(last.sections[3].action_items[0].due_date).toBe('2026-09-05');
  });
});
