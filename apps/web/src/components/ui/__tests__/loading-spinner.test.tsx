/**
 * LoadingSpinner — the status role, its LOCALISED screen-reader label and
 * variant styling.
 *
 * The default label used to be the literal string "Loading...", so every one of
 * the ~90 call sites that omit `label` announced English to a reader running
 * the app in French, German, Spanish, Italian or Chinese. A shared primitive
 * never hardcodes a user-facing string (apps/web/CLAUDE.md); it resolves it
 * from the active locale. `common.loading` already exists in all six locales,
 * so nothing new had to be translated.
 *
 * The global i18n stub echoes keys, so the resolved name reads `common.loading`
 * here rather than the French or English wording.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { LoadingSpinner } from '../loading-spinner';

describe('LoadingSpinner', () => {
  it('exposes a status role labelled from the active locale by default', () => {
    renderWithProviders(<LoadingSpinner />);
    expect(screen.getByRole('status', { name: 'common.loading' })).toBeInTheDocument();
  });

  it('accepts a custom screen-reader label', () => {
    renderWithProviders(<LoadingSpinner label="Fetching results" />);
    expect(screen.getByRole('status', { name: 'Fetching results' })).toBeInTheDocument();
  });

  it('keeps the status role so a loading section stays perceivable', () => {
    // Ten-plus suites use `getByRole('status')` to assert that a section is
    // loading — the role is the signal, not an implementation detail.
    renderWithProviders(<LoadingSpinner />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('maps size and colour variants to distinct styling', () => {
    const { rerender } = renderWithProviders(<LoadingSpinner size="sm" />);
    const small = screen.getByRole('status').getAttribute('class');
    rerender(<LoadingSpinner size="2xl" spinnerColor="destructive" />);
    expect(screen.getByRole('status').getAttribute('class')).not.toBe(small);
  });

  it('themes the success colour with the design token, not a raw palette value', () => {
    // `text-green-500` is fixed across the five colour themes and escapes the
    // contrast guard, which only covers `--color-*` pairs.
    renderWithProviders(<LoadingSpinner spinnerColor="success" />);
    const className = screen.getByRole('status').getAttribute('class') ?? '';
    expect(className).toContain('text-success');
    expect(className).not.toContain('green-500');
  });
});
