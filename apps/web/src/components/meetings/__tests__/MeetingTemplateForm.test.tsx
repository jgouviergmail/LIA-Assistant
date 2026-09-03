/**
 * The template form (ADR-259): validation is stated, never silent — a blank
 * name marks the field, an incomplete section blocks the submit with an
 * alert, and a save in flight cannot be submitted twice.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingTemplateUpdate } from '@/types/meetings';

import { MeetingTemplateForm } from '../MeetingTemplateForm';

function initial(over: Partial<MeetingTemplateUpdate> = {}): MeetingTemplateUpdate {
  return {
    name: 'Retro',
    description: null,
    category: 'custom',
    sections: [{ key: 'went_well', label: 'Went well', instruction: 'List it.', kind: 'bullets' }],
    ...over,
  };
}

function render(over: Partial<React.ComponentProps<typeof MeetingTemplateForm>> = {}) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  const utils = renderWithProviders(
    <MeetingTemplateForm
      lng="en"
      title="Edit"
      initial={initial()}
      isSaving={false}
      onSubmit={onSubmit}
      onCancel={onCancel}
      {...over}
    />
  );
  return { ...utils, onSubmit, onCancel };
}

describe('MeetingTemplateForm', () => {
  it('submits trimmed values, an empty description as null', async () => {
    const { user, onSubmit } = render();
    const name = screen.getByLabelText('meetings.templates.form.name');
    await user.clear(name);
    await user.type(name, '  Weekly  ');
    await user.type(screen.getByLabelText('meetings.templates.form.description'), '   ');
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Weekly',
      description: null,
      category: 'custom',
      sections: initial().sections,
    });
  });

  it('refuses a blank name and says so on the field', async () => {
    const { user, onSubmit } = render({ initial: initial({ name: '' }) });
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    expect(onSubmit).not.toHaveBeenCalled();
    const name = screen.getByLabelText('meetings.templates.form.name');
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('meetings.templates.form.name_missing');
  });

  it('refuses a section without instruction and keeps the reason visible', async () => {
    const { user, onSubmit } = render({
      initial: initial({
        sections: [{ key: 'went_well', label: 'Went well', instruction: '', kind: 'bullets' }],
      }),
    });
    await user.click(screen.getByRole('button', { name: 'common.save' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('meetings.templates.form.incomplete')).toBeInTheDocument();
  });

  it('shows the save in flight and cannot submit twice', async () => {
    const { user, onSubmit } = render({ isSaving: true });
    expect(screen.getByRole('form', { busy: true })).toBeInTheDocument();
    const save = screen.getByRole('button', { name: /common\.saving/ });
    expect(save).toBeDisabled();
    await user.click(save);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('cancels without submitting', async () => {
    const { user, onSubmit, onCancel } = render();
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
