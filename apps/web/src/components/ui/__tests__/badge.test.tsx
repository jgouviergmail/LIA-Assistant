/**
 * Badge — children, optional icon/pulse decorations and variant styling.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Badge } from '../badge';

describe('Badge', () => {
  it('renders its children', () => {
    renderWithProviders(<Badge>New</Badge>);
    expect(screen.getByText('New')).toBeInTheDocument();
  });

  it('renders a leading icon when provided', () => {
    renderWithProviders(<Badge icon={<span data-testid="dot" />}>Live</Badge>);
    expect(screen.getByTestId('dot')).toBeInTheDocument();
  });

  it('renders the pulse indicator only when pulse is set', () => {
    const { container, rerender } = renderWithProviders(<Badge>Idle</Badge>);
    expect(container.querySelector('.animate-ping')).toBeNull();
    rerender(<Badge pulse>Idle</Badge>);
    expect(container.querySelector('.animate-ping')).not.toBeNull();
  });

  it('maps the variant prop to distinct styling (default vs success)', () => {
    const { rerender } = renderWithProviders(<Badge variant="default">X</Badge>);
    const def = screen.getByText('X').className;
    rerender(<Badge variant="success">X</Badge>);
    expect(screen.getByText('X').className).not.toBe(def);
  });
});

/**
 * Every status variant is themed, and therefore guarded.
 *
 * `success` and `destructive` were the two exceptions: they painted
 * `bg-green-100 / dark:bg-green-900` and `bg-red-100 / dark:bg-red-900`, fixed
 * values that ignore the five colour themes and sit outside
 * `design-contrast.guard.test.ts`, which only reads `--color-*` pairs. Since
 * `lifecycleTone` routes most statuses to exactly those two, the exception was
 * about to become the rule.
 *
 * The comment that justified them — "solid opaque backgrounds to prevent
 * gradient bleed-through" — described a risk that no longer exists: measured
 * 2026-08-05, `Card variant="gradient"` has zero call sites.
 *
 * `alert` stays the only SOLID ground (ADR-205): the priority hierarchy still
 * separates `high` from `medium` by density, not by hue.
 */
describe('Badge — themed variants', () => {
  const STATUS_VARIANTS = [
    'default',
    'secondary',
    'success',
    'destructive',
    'warning',
    'alert',
    'info',
    'outline',
  ] as const;

  const RAW_PALETTE =
    /\b(?:bg|text|border)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950)\b/;

  it.each(STATUS_VARIANTS)('renders %s from design tokens, never a raw palette value', variant => {
    renderWithProviders(<Badge variant={variant}>Status</Badge>);
    expect(screen.getByText('Status').className).not.toMatch(RAW_PALETTE);
  });

  it('keeps alert as the only solid fill, so priority stays readable', () => {
    const { rerender } = renderWithProviders(<Badge variant="alert">High</Badge>);
    expect(screen.getByText('High').className).toContain('bg-destructive');
    expect(screen.getByText('High').className).not.toContain('bg-destructive/');

    rerender(<Badge variant="warning">Medium</Badge>);
    expect(screen.getByText('Medium').className).toContain('bg-warning/');
  });

  it('distinguishes success from destructive', () => {
    const { rerender } = renderWithProviders(<Badge variant="success">Done</Badge>);
    const done = screen.getByText('Done').className;
    rerender(<Badge variant="destructive">Failed</Badge>);
    expect(screen.getByText('Failed').className).not.toBe(done);
  });
});
