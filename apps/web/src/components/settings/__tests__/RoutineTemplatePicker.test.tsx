/**
 * A ready-made routine fills the create form in one choice (lot 13): its words in
 * the reader's language, its clock, its delivery — nothing scheduled until saved.
 */
import { useState } from 'react';
import { createInstance } from 'i18next';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { blankRoutineFields, type RoutineTemplateFields } from '@/lib/routine-templates';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { RoutineTemplatePicker } from '../RoutineTemplatePicker';

const english = createInstance();
await english.init({ lng: 'en', resources: { en: { translation: en } } });
const french = createInstance();
await french.init({ lng: 'fr', resources: { fr: { translation: fr } } });

const TODAY = '2026-11-13';

function Harness({ offered = true, t = english.t }: { offered?: boolean; t?: typeof english.t }) {
  const [form, setForm] = useState<RoutineTemplateFields>(blankRoutineFields(TODAY));
  return (
    <>
      <RoutineTemplatePicker offered={offered} form={form} setForm={setForm} today={TODAY} t={t} />
      <output aria-label="title">{form.title}</output>
      <output aria-label="instruction">{form.action_prompt}</output>
      <output aria-label="clock">{form.trigger_kind}</output>
      <output aria-label="quiet">{String(form.notify_only_when_new)}</output>
    </>
  );
}

describe('RoutineTemplatePicker', () => {
  it('names the list in the reader language, its purpose attached as its description', () => {
    renderWithProviders(<Harness />);
    const list = screen.getByRole('combobox', { name: en.scheduled_actions.templates.label });
    expect(list).toHaveValue('');
    expect(list).toHaveAccessibleDescription(en.scheduled_actions.templates.hint);

    renderWithProviders(<Harness t={french.t} />);
    expect(
      screen.getByRole('combobox', { name: fr.scheduled_actions.templates.label })
    ).toBeInTheDocument();
  });

  it('fills the form with the template chosen, and describes it', async () => {
    renderWithProviders(<Harness />);
    const list = screen.getByRole('combobox', { name: en.scheduled_actions.templates.label });

    await userEvent.selectOptions(list, 'inbox_triage');

    const triage = en.scheduled_actions.templates.inbox_triage;
    expect(screen.getByLabelText('title')).toHaveTextContent(triage.title);
    expect(screen.getByLabelText('instruction')).toHaveTextContent(triage.prompt);
    expect(screen.getByLabelText('quiet')).toHaveTextContent('true');
    expect(list).toHaveValue('inbox_triage');
    expect(list).toHaveAccessibleDescription(triage.description);
    // The list keeps the focus while what it describes changes.
    expect(list).toHaveFocus();
  });

  it('a condition template switches the clock to the watch', async () => {
    renderWithProviders(<Harness />);
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: en.scheduled_actions.templates.label }),
      'overdue_tasks'
    );
    expect(screen.getByLabelText('clock')).toHaveTextContent('condition');
  });

  it('going back to no template empties what the template filled', async () => {
    renderWithProviders(<Harness />);
    const list = screen.getByRole('combobox', { name: en.scheduled_actions.templates.label });
    await userEvent.selectOptions(list, 'weekly_review');

    await userEvent.selectOptions(list, '');

    expect(screen.getByLabelText('title')).toHaveTextContent('');
    expect(screen.getByLabelText('instruction')).toHaveTextContent('');
    expect(list).toHaveAccessibleDescription(en.scheduled_actions.templates.hint);
  });

  it('is not drawn where a routine is edited or duplicated', () => {
    renderWithProviders(<Harness offered={false} />);
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
