/**
 * CopyValueField — a value the person copies into another system (ADR-386).
 *
 * The value is READ whole, at any width: a long address or a secret wraps
 * rather than hiding behind a field's scroll on a phone. It is named by its
 * label as a group, its copy button by what it copies, and it is never offered
 * to the selection assist — selecting a secret must not hand it to a model.
 *
 * `renderWithProviders` runs `userEvent.setup()`, which installs its own
 * `navigator.clipboard` stub — so the clipboard spy is taken AFTER render.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { CopyValueField } from '../CopyValueField';

const SECRET = 'xQ3m-Zr8_vK2pL9tY6wB1nH4cF7dJ0sA5eG2uR8iO3k'; // gitleaks:allow

function spyClipboard() {
  if (!navigator.clipboard) {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: () => Promise.resolve() },
      configurable: true,
      writable: true,
    });
  }
  return vi.spyOn(navigator.clipboard, 'writeText');
}

function field() {
  return renderWithProviders(
    <CopyValueField
      id="the-secret"
      label="Secret"
      value={SECRET}
      copyLabel="Copy the secret"
      copiedMessage="Secret copied."
    />
  );
}

beforeEach(() => vi.clearAllMocks());

describe('CopyValueField', () => {
  it('shows the whole value, named by its label', () => {
    field();

    const group = screen.getByRole('group', { name: 'Secret' });
    expect(group).toHaveTextContent(SECRET);
    // Wraps at any width: never a field whose end a narrow screen hides.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByText(SECRET)).toHaveClass('break-all');
  });

  it('keeps the value away from the selection assist', () => {
    field();

    expect(screen.getByText(SECRET).closest('[data-selection-assist="off"]')).not.toBeNull();
  });

  it('copies the value with a button named after it, and says so', async () => {
    const { user } = field();
    const writeText = spyClipboard().mockResolvedValue(undefined);

    await user.click(screen.getByRole('button', { name: 'Copy the secret' }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SECRET));
    expect(toast.success).toHaveBeenCalledWith('Secret copied.');
  });

  it('says when the browser refuses the copy', async () => {
    const { user } = field();
    spyClipboard().mockRejectedValue(new Error('denied'));

    await user.click(screen.getByRole('button', { name: 'Copy the secret' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.copyFailed'));
    expect(toast.success).not.toHaveBeenCalled();
  });
});
