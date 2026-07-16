/**
 * CodeBlock — renders the code (plain fallback for an unknown language) and the
 * copy-to-clipboard action (success + failure).
 *
 * `renderWithProviders` runs `userEvent.setup()`, which installs its own
 * `navigator.clipboard` stub — so the clipboard spy is taken AFTER render.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { CodeBlock } from '../CodeBlock';

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

beforeEach(() => vi.clearAllMocks());

describe('CodeBlock', () => {
  it('renders the language label and the code content', () => {
    renderWithProviders(<CodeBlock language="text">const a = 1;</CodeBlock>);
    expect(screen.getByText('text')).toBeInTheDocument();
    expect(screen.getByText('const a = 1;')).toBeInTheDocument();
  });

  it('copies the code to the clipboard and toasts success', async () => {
    const { user } = renderWithProviders(<CodeBlock language="text">copy me</CodeBlock>);
    const writeText = spyClipboard().mockResolvedValue(undefined);
    await user.click(screen.getByRole('button', { name: 'chat.code.copy' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('copy me'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('toasts an error when the clipboard write fails', async () => {
    const { user } = renderWithProviders(<CodeBlock language="text">copy me</CodeBlock>);
    // Throw synchronously (not a floating rejected promise) so vitest's
    // unhandled-rejection detector can never race the component's try/catch.
    spyClipboard().mockImplementation(() => {
      throw new Error('denied');
    });
    await user.click(screen.getByRole('button', { name: 'chat.code.copy' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});
