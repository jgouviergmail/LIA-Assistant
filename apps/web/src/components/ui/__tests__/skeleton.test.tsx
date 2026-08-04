/**
 * Skeleton — a decorative placeholder, themed, and silent unless asked to speak.
 *
 * Three defects lived here together:
 *
 *  - **Announced in English.** `aria-label="Loading..."` plus an `sr-only`
 *    "Loading..." shipped a hardcoded string to six locales. A hook cannot fix
 *    it: `app/[lng]/dashboard/{settings,spaces}/loading.tsx` are App Router
 *    SERVER components that render `<Skeleton>`, and a client hook there is a
 *    build error. So the primitive stops inventing a string instead.
 *  - **One live region per block.** `TableSkeleton` nests a `role="status"`
 *    skeleton per cell — 24 live regions for a five-row table, inside another
 *    live region. A skeleton is a picture of the layout to come; the page says
 *    once that it is loading, not once per rectangle.
 *  - **Off-theme, and broken in dark mode.** `bg-gray-200 dark:bg-gray-700`
 *    ignores the five colour themes, and `CardSkeleton`'s `bg-white` painted a
 *    white card on a dark background.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { CardSkeleton, Skeleton, TableSkeleton } from '../skeleton';

describe('Skeleton', () => {
  it('is decorative by default: no live region, no announced text', () => {
    const { container } = renderWithProviders(<Skeleton className="h-4 w-10" />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
    expect(container.textContent).toBe('');
  });

  it('announces only when the caller supplies a label', () => {
    renderWithProviders(<Skeleton label="Loading the table" />);
    expect(screen.getByRole('status', { name: 'Loading the table' })).toBeInTheDocument();
  });

  it('uses theme tokens rather than a fixed grey', () => {
    const { container } = renderWithProviders(<Skeleton />);
    const className = container.firstElementChild?.getAttribute('class') ?? '';
    expect(className).toContain('bg-muted');
    expect(className).not.toContain('gray-200');
    expect(className).not.toContain('gray-700');
  });

  it('keeps caller classes', () => {
    const { container } = renderWithProviders(<Skeleton className="h-8 w-32" />);
    expect(container.firstElementChild).toHaveClass('h-8', 'w-32');
  });
});

describe('TableSkeleton', () => {
  it('exposes at most one live region for the whole table', () => {
    renderWithProviders(<TableSkeleton rows={5} label="Loading rows" />);
    expect(screen.getAllByRole('status')).toHaveLength(1);
  });

  it('is silent when no label is given', () => {
    renderWithProviders(<TableSkeleton rows={3} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('renders the requested number of rows', () => {
    const { container } = renderWithProviders(<TableSkeleton rows={3} />);
    // header + 3 rows, 4 cells each
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(16);
  });
});

describe('CardSkeleton', () => {
  it('uses the card surface token, so it follows dark mode', () => {
    const { container } = renderWithProviders(<CardSkeleton />);
    const className = container.firstElementChild?.getAttribute('class') ?? '';
    expect(className).toContain('bg-card');
    expect(className).not.toContain('bg-white');
  });

  it('is silent when no label is given', () => {
    renderWithProviders(<CardSkeleton />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
