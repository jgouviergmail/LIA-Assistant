/**
 * Button — variant wiring, the loading state (disabled + spinner + optional
 * text), the `asChild` slot polymorphism and click dispatch.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Button } from '../button';

describe('Button — rendering', () => {
  it('renders a native button carrying its children', () => {
    renderWithProviders(<Button>Save</Button>);
    const btn = screen.getByRole('button', { name: 'Save' });
    expect(btn.tagName).toBe('BUTTON');
  });

  it('maps the variant prop to distinct styling (default vs destructive)', () => {
    const { rerender } = renderWithProviders(<Button variant="default">X</Button>);
    expect(screen.getByRole('button').className).toContain('bg-primary');
    rerender(<Button variant="destructive">X</Button>);
    expect(screen.getByRole('button').className).toContain('bg-destructive');
  });
});

describe('Button — loading state', () => {
  it('disables the button and shows a spinner while loading', () => {
    renderWithProviders(<Button isLoading>Save</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
    // The spinner exposes role="status"; the label text is not rendered here.
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders the loading text when provided', () => {
    renderWithProviders(
      <Button isLoading loadingText="Saving…">
        Save
      </Button>
    );
    expect(screen.getByText('Saving…')).toBeInTheDocument();
  });
});

describe('Button — disabled', () => {
  it('does not fire onClick when disabled', async () => {
    const onClick = vi.fn();
    const { user } = renderWithProviders(
      <Button disabled onClick={onClick}>
        Save
      </Button>
    );
    await user.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('Button — interaction & polymorphism', () => {
  it('fires onClick when pressed', async () => {
    const onClick = vi.fn();
    const { user } = renderWithProviders(<Button onClick={onClick}>Go</Button>);
    await user.click(screen.getByRole('button', { name: 'Go' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('asChild renders the provided element instead of a button, keeping button classes', () => {
    renderWithProviders(
      <Button asChild variant="outline">
        <a href="https://example.com/next">Continue</a>
      </Button>
    );
    const link = screen.getByRole('link', { name: 'Continue' });
    expect(link).toHaveAttribute('href', 'https://example.com/next');
    expect(link.className).toContain('inline-flex');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
