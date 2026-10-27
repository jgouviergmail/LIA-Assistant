import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';

// Hold the menu's automatic focus return behind the picker opening. This is
// the ordering that races in the browser: the selected menu item disappears,
// so the dialog must not depend on that transient node as its opener.
// Both the menu and dialog otherwise retain their real Radix behavior.
vi.mock('@/components/ui/dropdown-menu', async importOriginal => {
  const actual = await importOriginal<typeof import('@/components/ui/dropdown-menu')>();
  return {
    ...actual,
    DropdownMenuContent: forwardRef<
      ElementRef<typeof actual.DropdownMenuContent>,
      ComponentPropsWithoutRef<typeof actual.DropdownMenuContent>
    >(function MenuWithoutEarlyFocusReturn({ onCloseAutoFocus, ...props }, ref) {
      return (
        <actual.DropdownMenuContent
          {...props}
          ref={ref}
          onCloseAutoFocus={event => {
            onCloseAutoFocus?.(event);
            event.preventDefault();
          }}
        />
      );
    }),
  };
});

interface PickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Data fetching/copying belongs to each picker's own tests. Keep the real
// controlled modal, Escape/close handling and shared focus-return primitive.
function PickerDialog({ open, onOpenChange }: PickerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Choose an attachment source</DialogTitle>
        <DialogDescription>Picker focus regression fixture.</DialogDescription>
        <input aria-label="Picker search" />
      </DialogContent>
    </Dialog>
  );
}

vi.mock('@/components/chat/KnowledgeDocumentPickerDialog', () => ({
  KnowledgeDocumentPickerDialog: (props: PickerProps) => <PickerDialog {...props} />,
}));
vi.mock('@/components/chat/BookmarkPickerDialog', () => ({
  BookmarkPickerDialog: (props: PickerProps) => <PickerDialog {...props} />,
}));
vi.mock('@/components/chat/GeneratedFilePickerDialog', () => ({
  GeneratedFilePickerDialog: (props: PickerProps) => <PickerDialog {...props} />,
}));
vi.mock('@/components/meetings/MeetingImportDialog', () => ({
  MeetingImportDialog: (props: PickerProps) => <PickerDialog {...props} />,
}));
vi.mock('@/lib/native/shell', () => ({ isAndroidShell: () => false }));

import { ComposerAttachmentsControl } from '../ComposerAttachmentsControl';

describe.each([
  ['knowledge', 'from_knowledge'],
  ['bookmark', 'from_bookmark'],
  ['generated', 'from_generated'],
  ['meeting_import', 'import_meeting'],
])('composer picker %s focus return', (_picker, entry) => {
  it.each(['Escape', 'Close'] as const)(
    'returns focus to the persistent attachment button after %s',
    async closeMode => {
      const { user } = renderWithProviders(
        <ComposerAttachmentsControl
          t={key => key}
          attachmentsEnabled
          knowledgeDocumentsEnabled
          bookmarksEnabled
          generatedFilesEnabled
          meetingImportEnabled
          disabled={false}
          onPickFile={vi.fn()}
          onTakePhoto={vi.fn()}
          remaining={5}
          onAttached={() => ({ ok: true })}
        />
      );
      const trigger = screen.getByRole('button', { name: 'chat.attachments.add' });
      if (closeMode === 'Escape') await user.click(trigger);
      else {
        act(() => trigger.focus());
        await user.keyboard('{Enter}');
      }
      const menu = await screen.findByRole('menu');
      const transientItem = within(menu).getByRole('menuitem', {
        name: `chat.attachments.${entry}`,
      });
      act(() => transientItem.focus());
      expect(transientItem).toHaveFocus();
      if (closeMode === 'Escape') await user.click(transientItem);
      else await user.keyboard('{Enter}');

      const dialog = await screen.findByRole('dialog', { name: 'Choose an attachment source' });
      expect(transientItem).not.toBeInTheDocument();
      await user.click(within(dialog).getByRole('textbox', { name: 'Picker search' }));
      if (closeMode === 'Escape') await user.keyboard('{Escape}');
      else await user.click(within(dialog).getByRole('button', { name: 'common.close' }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      await waitFor(() => expect(trigger).toHaveFocus());
    }
  );
});
