/**
 * AlertDialogAction / AlertDialogCancel — the confirm button says what it does.
 *
 * `AlertDialogAction` rendered `buttonVariants()` with no variant, so the
 * button that confirms an IRREVERSIBLE deletion came out in the same primary
 * blue as "Save". It also accepted no `variant` prop, so the only way to make
 * it red was to re-write the classes at the call site — the very pattern
 * ADR-205 removed from status badges. Eight call sites did exactly that, and
 * they drifted immediately:
 *
 *   - four wrote `bg-destructive text-destructive-foreground hover:…`
 *   - three wrote `bg-destructive hover:…` and FORGOT the foreground token, so
 *     the label kept `text-primary-foreground` and its contrast was nobody's
 *     responsibility
 *   - one wrote `bg-orange-600`, a raw palette value outside the five themes
 *     and outside the contrast guard
 *
 * while twenty-two others wrote nothing at all and stayed blue.
 *
 * So the variant is a PROP, resolved by `buttonVariants` like every other
 * button in the app, and it inherits the guard with it.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../alert-dialog';
import { buttonVariants } from '../button';

function renderDialog(action: React.ReactNode, cancel?: React.ReactNode) {
  return renderWithProviders(
    <AlertDialog open>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete everything?</AlertDialogTitle>
          <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          {cancel ?? <AlertDialogCancel>Cancel</AlertDialogCancel>}
          {action}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

describe('AlertDialogAction', () => {
  it('accepts a variant and renders the design-system classes for it', () => {
    renderDialog(<AlertDialogAction variant="destructive">Delete</AlertDialogAction>);
    const confirm = screen.getByRole('button', { name: 'Delete' });
    expect(confirm.className).toBe(buttonVariants({ variant: 'destructive' }));
  });

  it('carries the destructive FOREGROUND token, not just the background', () => {
    // Three call sites wrote `bg-destructive` without it, leaving the label on
    // `text-primary-foreground` with nobody checking the pair.
    renderDialog(<AlertDialogAction variant="destructive">Delete</AlertDialogAction>);
    const confirm = screen.getByRole('button', { name: 'Delete' });
    expect(confirm.className).toContain('bg-destructive');
    expect(confirm.className).toContain('text-destructive-foreground');
  });

  it('supports the warning variant, for a lesser destruction beside a greater one', () => {
    // "Delete all except pinned" next to "Delete all" — the hierarchy used to
    // be drawn with a raw `bg-orange-600`.
    renderDialog(<AlertDialogAction variant="warning">Keep pinned</AlertDialogAction>);
    const confirm = screen.getByRole('button', { name: 'Keep pinned' });
    expect(confirm.className).toContain('bg-warning');
    expect(confirm.className).toContain('text-warning-foreground');
    expect(confirm.className).not.toContain('orange');
  });

  it('still defaults to the primary action when no variant is given', () => {
    renderDialog(<AlertDialogAction>Confirm</AlertDialogAction>);
    expect(screen.getByRole('button', { name: 'Confirm' }).className).toBe(buttonVariants());
  });

  it('keeps caller classes alongside the variant', () => {
    renderDialog(
      <AlertDialogAction variant="destructive" className="w-full">
        Delete
      </AlertDialogAction>
    );
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveClass('w-full');
  });
});

describe('AlertDialogCancel', () => {
  it('stays neutral by default — dismissing a dialog destroys nothing', () => {
    renderDialog(<AlertDialogAction variant="destructive">Delete</AlertDialogAction>);
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    expect(cancel.className).toContain('border-2');
    expect(cancel.className).not.toContain('bg-destructive');
  });

  it('accepts a variant override', () => {
    renderDialog(
      <AlertDialogAction>Confirm</AlertDialogAction>,
      <AlertDialogCancel variant="ghost">Cancel</AlertDialogCancel>
    );
    expect(screen.getByRole('button', { name: 'Cancel' }).className).toContain(
      buttonVariants({ variant: 'ghost' }).split(' ')[0]
    );
  });
});
