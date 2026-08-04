/**
 * EmptyState — one shape for "there is nothing here", and a way out.
 *
 * Seven empty states were written seven different ways: four vertical paddings
 * (py-6 / py-8 / py-12 / p-12), two icon sizes, four different ways to fade the
 * icon (`text-muted-foreground`, `/50`, `opacity-30`, `opacity-50`), a dashed
 * border on two of them — and, more importantly, only ONE of the seven offered
 * an action. The other six were dead ends: a user reading "no connection yet"
 * had no way to create one from where they stood.
 *
 * So the component carries the doctrine, not just the pixels:
 *  - `variant="page"` REQUIRES an action (enforced by the types),
 *  - `reason` separates "you have no data" from "your filter matched nothing",
 *    because those two need different words and different exits.
 */

import { describe, it, expect, vi } from 'vitest';
import { Plus, Users } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { EmptyState } from '../empty-state';

describe('EmptyState — content', () => {
  it('renders the description as the message of record', () => {
    renderWithProviders(<EmptyState description="No relations yet" />);
    expect(screen.getByText('No relations yet')).toBeInTheDocument();
  });

  it('renders an optional title above the description', () => {
    renderWithProviders(<EmptyState title="No spaces" description="Create one to begin" />);
    expect(screen.getByText('No spaces')).toBeInTheDocument();
    expect(screen.getByText('Create one to begin')).toBeInTheDocument();
  });

  it('does not inject a heading — the host owns the document outline', () => {
    // A fixed level cannot be right everywhere: on the Spaces screen an <h3>
    // followed the page <h1> with no <h2> between them, which is the heading
    // -order defect this lot exists to remove.
    renderWithProviders(<EmptyState title="No spaces" description="Create one" />);
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
  });

  it('hides the icon from assistive tech — the words carry the meaning', () => {
    const { container } = renderWithProviders(<EmptyState icon={Users} description="Nothing" />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders no icon when none is given', () => {
    const { container } = renderWithProviders(<EmptyState description="Nothing" />);
    expect(container.querySelector('svg')).toBeNull();
  });
});

describe('EmptyState — the way out', () => {
  it('renders the action as a real button and calls it', async () => {
    const onClick = vi.fn();
    const { user } = renderWithProviders(
      <EmptyState
        variant="page"
        title="No spaces"
        description="Create one"
        action={{ label: 'Create a space', onClick }}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Create a space' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('renders a link action as a link, not a button', () => {
    renderWithProviders(
      <EmptyState
        variant="page"
        title="Nothing"
        description="Go elsewhere"
        action={{ label: 'Open settings', href: '/settings' }}
      />
    );
    expect(screen.getByRole('link', { name: 'Open settings' })).toHaveAttribute(
      'href',
      '/settings'
    );
  });

  it('carries an optional icon on the action, so a twin button elsewhere matches', () => {
    // The Spaces screen shows "Create a space" twice — in the header and in the
    // empty state. They must look like the same action.
    const { container } = renderWithProviders(
      <EmptyState
        variant="page"
        title="No spaces"
        description="Create one"
        action={{ label: 'Create a space', onClick: vi.fn(), icon: Plus }}
      />
    );
    expect(container.querySelector('button svg')).toBeInTheDocument();
  });

  it('a section variant may legitimately have no action', () => {
    renderWithProviders(<EmptyState description="Nothing here" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('EmptyState — reason', () => {
  it('marks a no-match state so a filter reset can be offered instead', () => {
    renderWithProviders(<EmptyState reason="no-match" description="No result" />);
    expect(screen.getByTestId('empty-state')).toHaveAttribute('data-reason', 'no-match');
  });

  it('defaults to no-data', () => {
    renderWithProviders(<EmptyState description="Nothing" />);
    expect(screen.getByTestId('empty-state')).toHaveAttribute('data-reason', 'no-data');
  });
});

describe('EmptyState — presentation', () => {
  it('gives the page variant its own framing, distinct from a section', () => {
    const { container: page } = renderWithProviders(
      <EmptyState
        variant="page"
        title="T"
        description="D"
        action={{ label: 'Go', onClick: vi.fn() }}
      />
    );
    const pageClasses = page.querySelector('[data-testid="empty-state"]')?.className ?? '';

    const { container: section } = renderWithProviders(<EmptyState description="D" />);
    const sectionClasses = section.querySelector('[data-testid="empty-state"]')?.className ?? '';

    expect(pageClasses).toContain('border-dashed');
    expect(sectionClasses).not.toContain('border-dashed');
  });

  it('fades the icon through one token, not an ad-hoc opacity', () => {
    const { container } = renderWithProviders(<EmptyState icon={Users} description="D" />);
    const icon = container.querySelector('svg');
    expect(icon?.getAttribute('class')).toContain('text-muted-foreground');
    expect(icon?.getAttribute('class')).not.toContain('opacity-');
  });
});
