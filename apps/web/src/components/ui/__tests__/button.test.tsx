/**
 * Button — stable loading name/focus, guarded activation, slot polymorphism.
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
  it('keeps its name and focus while preventing another activation during loading', async () => {
    const onClick = vi.fn();
    const { rerender, user } = renderWithProviders(<Button onClick={onClick}>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    button.focus();
    rerender(
      <Button isLoading onClick={onClick}>
        Save
      </Button>
    );
    expect(button).toHaveFocus();
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveAttribute('aria-disabled', 'true');
    await user.click(button);
    await user.keyboard('{Enter}');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('renders the loading text when provided', () => {
    renderWithProviders(
      <Button isLoading loadingText="Saving…">
        Save
      </Button>
    );
    expect(screen.getByRole('button', { name: 'Save' })).toHaveAccessibleDescription('Saving…');
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

  it('guards the slotted link handler while loading without replacing its child', async () => {
    const onClick = vi.fn();
    const { user } = renderWithProviders(
      <Button asChild isLoading>
        <a href="#next" onClick={onClick}>
          Continue
        </a>
      </Button>
    );
    const link = screen.getByRole('link', { name: 'Continue' });
    link.focus();
    await user.click(link);
    await user.keyboard('{Enter}');
    expect(link).toHaveFocus();
    expect(onClick).not.toHaveBeenCalled();
  });
});
