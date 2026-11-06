/**
 * Where a selection goes (ADR-369, lot 4): what is listed and a view are not offered,
 * the trash and the spam have their own buttons, a nested folder sits under its parent.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MailFolder } from '@/lib/workbench/types';

import { MoveDialog } from '../MoveDialog';

const system = (role: MailFolder['role']): MailFolder => ({
  id: `system:${role}`,
  kind: 'system',
  role,
  name: null,
});
const own = (name: string): MailFolder => ({ id: name, kind: 'user', role: null, name });

const FOLDERS: MailFolder[] = [
  system('inbox'),
  system('starred'),
  system('sent'),
  system('archive'),
  system('spam'),
  system('trash'),
  own('Projets'),
  own('Projets/2026'),
];

function dialog(
  listed: string,
  folders: MailFolder[] = FOLDERS,
  moving: string[] | null = ['m1', 'm2']
) {
  const onPick = vi.fn();
  const onClose = vi.fn();
  const rendered = renderWithProviders(
    <MoveDialog
      lng="en"
      moving={moving}
      folders={folders}
      listed={listed}
      labels={false}
      onPick={onPick}
      onClose={onClose}
    />
  );
  return { ...rendered, onPick, onClose };
}

describe('MoveDialog', () => {
  it('stays closed until messages are asked to move', () => {
    dialog('system:inbox', FOLDERS, null);

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('offers the places a message sits in, never what is listed nor a view', () => {
    dialog('system:inbox');

    expect(screen.getByRole('button', { name: 'workbench.mail.folders.archive' })).toBeVisible();
    for (const role of ['inbox', 'starred', 'sent', 'spam', 'trash']) {
      expect(screen.queryByRole('button', { name: `workbench.mail.folders.${role}` })).toBeNull();
    }
  });

  it('offers the inbox from elsewhere', () => {
    dialog('Projets');

    expect(screen.getByRole('button', { name: 'workbench.mail.folders.inbox' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Projets' })).toBeNull();
  });

  it('draws a nested folder under its parent, and names it whole', () => {
    dialog('system:inbox');

    const nested = screen.getByRole('button', { name: 'Projets/2026' });

    expect(nested).toHaveTextContent('2026');
    expect(nested).not.toHaveTextContent('Projets');
  });

  it('hands back the folder picked', async () => {
    const { user, onPick } = dialog('system:inbox');

    await user.click(screen.getByRole('button', { name: 'Projets' }));

    expect(onPick).toHaveBeenCalledWith('Projets');
  });

  it('says when there is nowhere else to go', () => {
    dialog('system:inbox', [system('inbox'), system('trash')]);

    expect(screen.getByText('workbench.mail.move_nowhere')).toBeInTheDocument();
  });
});
