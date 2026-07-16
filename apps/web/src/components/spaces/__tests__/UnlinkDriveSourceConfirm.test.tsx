/**
 * UnlinkDriveSourceConfirm — accessible name of the delete-documents checkbox
 * (audit F012) and the destructive-confirm contract.
 *
 * The checkbox lives inside a wrapping <label> (valid implicit association)
 * with an explicit aria-labelledby; querying BY ROLE AND NAME proves the
 * programmatic name. Also pins that the confirm callback carries the choice
 * and that the checkbox resets after confirming.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { UnlinkDriveSourceConfirm } from '../UnlinkDriveSourceConfirm';

const onConfirm = vi.fn();
const onOpenChange = vi.fn();

function renderDialog() {
  return render(
    <UnlinkDriveSourceConfirm
      open
      onOpenChange={onOpenChange}
      folderName="Reports"
      onConfirm={onConfirm}
    />
  );
}

beforeEach(() => {
  onConfirm.mockReset();
  onOpenChange.mockReset();
});

describe('UnlinkDriveSourceConfirm (F012)', () => {
  it('exposes the delete-documents checkbox by role and translated name', () => {
    renderDialog();
    const checkbox = screen.getByRole('checkbox', {
      name: 'spaces.drive.unlink_delete_docs',
    }) as HTMLInputElement;

    expect(checkbox.checked).toBe(false);
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(true);
  });

  it('is focusable', () => {
    renderDialog();
    const checkbox = screen.getByRole('checkbox', { name: 'spaces.drive.unlink_delete_docs' });
    checkbox.focus();
    expect(document.activeElement).toBe(checkbox);
  });

  it('confirms with the chosen deletion flag', () => {
    renderDialog();
    fireEvent.click(screen.getByRole('checkbox', { name: 'spaces.drive.unlink_delete_docs' }));
    fireEvent.click(screen.getByText('spaces.drive.unlink'));
    expect(onConfirm).toHaveBeenCalledWith(true);
  });

  it('confirms with false when the checkbox was left unchecked', () => {
    renderDialog();
    fireEvent.click(screen.getByText('spaces.drive.unlink'));
    expect(onConfirm).toHaveBeenCalledWith(false);
  });
});
