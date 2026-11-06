/**
 * The person's own Gmail labels (ADR-369, spec §6.3): created and renamed with
 * the name trimmed, deleted only once confirmed (the messages stay), one act at
 * a time, and a refused act keeps what was typed so nothing is retyped.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
} from '@/__tests__/test-utils';
import type { MailFolder } from '@/lib/workbench/types';

const { i18n } = vi.hoisted(() => ({
  // One stable `t` that shows its values, so each row's controls are told apart.
  i18n: {
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}(${Object.values(values).join('|')})` : key,
    i18n: { language: 'en' },
  },
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => i18n }));

import { LabelsManager } from '../LabelsManager';

const LABELS: MailFolder[] = [
  { id: 'Label_7', kind: 'user', role: null, name: 'Work' },
  { id: 'Label_8', kind: 'user', role: null, name: 'Work/Clients' },
];

function manager(labels: MailFolder[] = LABELS) {
  const acts = {
    onCreate: vi.fn().mockResolvedValue(undefined),
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
  };
  const rendered = renderWithProviders(
    <LabelsManager lng="en" open onOpenChange={vi.fn()} labels={labels} {...acts} />
  );
  return { ...rendered, ...acts };
}

const field = () => screen.getByLabelText('workbench.mail.labels.new');
const create = () => screen.getByRole('button', { name: 'workbench.mail.labels.create' });

describe('LabelsManager — a mailbox with folders', () => {
  const NESTED: MailFolder[] = [
    { id: 'Projets/2026', kind: 'user', role: null, name: 'Projets/2026' },
  ];

  function folderManager(labels: MailFolder[] = NESTED) {
    const onRename = vi.fn().mockResolvedValue(undefined);
    const rendered = renderWithProviders(
      <LabelsManager
        lng="en"
        open
        onOpenChange={vi.fn()}
        labels={labels}
        kind="folders"
        onCreate={vi.fn().mockResolvedValue(undefined)}
        onRename={onRename}
        onDelete={vi.fn().mockResolvedValue(undefined)}
      />
    );
    return { ...rendered, onRename };
  }

  it('speaks of folders, never of labels', () => {
    folderManager([]);

    expect(screen.getByRole('dialog', { name: 'workbench.mail.manage_folders' })).toBeVisible();
    expect(screen.getByText('workbench.mail.folder_manager.none')).toBeInTheDocument();
    expect(screen.queryByText(/workbench\.mail\.labels\./)).toBeNull();
  });

  it('renames a folder by its own name, its place kept', async () => {
    const { user, onRename } = folderManager();

    await user.click(
      screen.getByRole('button', { name: 'workbench.mail.folder_manager.rename(Projets/2026)' })
    );
    const field = screen.getByRole('textbox', {
      name: 'workbench.mail.folder_manager.rename_field(Projets/2026)',
    });

    expect(field).toHaveValue('2026');
    await user.clear(field);
    await user.type(field, '2027');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.folder_manager.save' }));

    expect(onRename).toHaveBeenCalledWith('Projets/2026', '2027');
  });
});

describe('LabelsManager', () => {
  it('lists the person’s labels, and says when there is none', () => {
    const listed = manager();
    expect(screen.getByText('Work')).toBeInTheDocument();
    expect(screen.getByText('Work/Clients')).toBeInTheDocument();
    listed.unmount();

    manager([]);
    expect(screen.getByText('workbench.mail.no_labels')).toBeInTheDocument();
  });

  it('creates a label with its name trimmed, then empties the field', async () => {
    const { user, onCreate } = manager();

    await user.click(create());
    await user.type(field(), '   ');
    await user.click(create());
    expect(onCreate).not.toHaveBeenCalled();

    await user.clear(field());
    await user.type(field(), '  Travel/2026  ');
    await user.click(create());

    expect(onCreate).toHaveBeenCalledWith('Travel/2026');
    await waitFor(() => expect(field()).toHaveValue(''));
  });

  it('keeps a refused name, and runs one act at a time', async () => {
    let refuse: (reason: Error) => void = () => undefined;
    const { user, onCreate, onDelete } = manager();
    onCreate.mockImplementationOnce(() => new Promise<void>((_, reject) => (refuse = reject)));

    await user.type(field(), 'Work');
    await user.click(create());
    fireEvent.submit(field().closest('form') as HTMLFormElement);
    await user.click(screen.getByRole('button', { name: 'workbench.mail.labels.delete(Work)' }));
    await answerConfirmDialog(user, true);
    refuse(new Error('label_name_taken'));

    await waitFor(() => expect(create()).not.toHaveAttribute('aria-busy'));
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onDelete).not.toHaveBeenCalled();
    expect(field()).toHaveValue('Work');
  });

  it('renames a label in place, its field taking the focus, the name trimmed', async () => {
    const { user, onRename } = manager();

    await user.click(screen.getByRole('button', { name: 'workbench.mail.labels.rename(Work)' }));
    const rename = screen.getByLabelText('workbench.mail.labels.rename_field(Work)');
    expect(rename).toHaveFocus();
    expect(rename).toHaveValue('Work');
    await user.clear(rename);
    await user.type(rename, '  Office  ');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.labels.save' }));

    expect(onRename).toHaveBeenCalledWith('Label_7', 'Office');
    await waitFor(() =>
      expect(screen.queryByLabelText('workbench.mail.labels.rename_field(Work)')).toBeNull()
    );
  });

  it('stays in the field when a rename is refused or empty, and cancels without sending', async () => {
    const { user, onRename } = manager();
    onRename.mockRejectedValueOnce(new Error('label_name_taken'));

    await user.click(screen.getByRole('button', { name: 'workbench.mail.labels.rename(Work)' }));
    const rename = screen.getByLabelText('workbench.mail.labels.rename_field(Work)');
    await user.clear(rename);
    await user.type(rename, 'Work/Clients');
    await user.click(screen.getByRole('button', { name: 'workbench.mail.labels.save' }));
    await waitFor(() => expect(onRename).toHaveBeenCalledTimes(1));
    expect(rename).toHaveValue('Work/Clients');

    await user.clear(rename);
    await user.click(screen.getByRole('button', { name: 'workbench.mail.labels.save' }));
    expect(onRename).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(screen.queryByLabelText('workbench.mail.labels.rename_field(Work)')).toBeNull();
    expect(onRename).toHaveBeenCalledTimes(1);
  });

  it('deletes a label only once confirmed', async () => {
    const { user, onDelete } = manager();
    const remove = screen.getByRole('button', {
      name: 'workbench.mail.labels.delete(Work/Clients)',
    });

    await user.click(remove);
    await answerConfirmDialog(user, false);
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(remove);
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith('Label_8'));
  });
});
