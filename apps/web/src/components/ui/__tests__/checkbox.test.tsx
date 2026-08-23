/**
 * Checkbox — the native control, themed.
 *
 * The product had three hand-rolled `<input type="checkbox">` carrying
 * `text-primary-600 focus:ring-primary-500 border-gray-300`. Measured
 * 2026-08-23: `primary-600` and `primary-500` produce ZERO rules in the
 * compiled CSS — the palette exposes `--color-primary`, not a numeric ramp — so
 * those boxes had no accent colour and, more seriously, no focus ring at all.
 * `border-gray-300` had no dark variant either.
 *
 * Deliberately wraps the NATIVE input rather than a Radix primitive: it keeps
 * form semantics (`checked`, `required`, form submission, browser autofill) for
 * free, adds no dependency, and avoids the container/host lockfile split that
 * `pnpm add` inside the dev container is known to cause.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Checkbox } from '../checkbox';

describe('Checkbox', () => {
  it('renders a real checkbox input', () => {
    renderWithProviders(<Checkbox aria-label="Remember me" />);
    const box = screen.getByRole('checkbox', { name: 'Remember me' });
    expect(box).toBeInTheDocument();
    expect(box.tagName).toBe('INPUT');
    expect(box).toHaveAttribute('type', 'checkbox');
  });

  it('uses palette tokens, never the numeric ramp that compiles to nothing', () => {
    renderWithProviders(<Checkbox aria-label="x" />);
    const cls = screen.getByRole('checkbox').className;
    expect(cls).not.toContain('primary-600');
    expect(cls).not.toContain('primary-500');
    expect(cls).toContain('accent-primary');
  });

  it('has a visible focus ring bound to the ring token', () => {
    renderWithProviders(<Checkbox aria-label="x" />);
    const cls = screen.getByRole('checkbox').className;
    expect(cls).toContain('focus-visible:ring-2');
    expect(cls).toContain('focus-visible:ring-ring');
  });

  it('borders on a token that already re-declares itself in dark mode', () => {
    // `border-gray-300` needed a `dark:` twin; `border-input` does not —
    // `--color-input` is redefined inside `.dark`, so one class covers both
    // modes. A `dark:border-input` here would compile to the same declaration.
    renderWithProviders(<Checkbox aria-label="x" />);
    const cls = screen.getByRole('checkbox').className;
    expect(cls).toContain('border-input');
    expect(cls).not.toContain('dark:border-input');
    expect(cls).not.toContain('gray-300');
  });

  it('keeps the native 16x16 box and grows no target with a pseudo-element', () => {
    // Measured 2026-08-23 across Chromium/Firefox/WebKit: a centred 24x24
    // `::before` extends the hit area in two engines and does nothing in
    // Firefox. Pinned as an anti-regression so the trick is not reintroduced.
    renderWithProviders(<Checkbox aria-label="x" />);
    const box = screen.getByRole('checkbox').className;
    expect(box).toContain('h-4 w-4');
    expect(box).not.toContain('before:');
  });

  it('forwards checked/onChange like the native control it replaces', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <Checkbox aria-label="x" checked={false} onChange={onChange} />
    );
    await user.click(screen.getByRole('checkbox'));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('honours disabled', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <Checkbox aria-label="x" disabled checked={false} onChange={onChange} />
    );
    await user.click(screen.getByRole('checkbox'));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });

  it('forwards a ref to the input so forms can focus it', () => {
    const ref = { current: null as HTMLInputElement | null };
    renderWithProviders(<Checkbox aria-label="x" ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it('merges an extra className without dropping its own', () => {
    renderWithProviders(<Checkbox aria-label="x" className="mt-1" />);
    const cls = screen.getByRole('checkbox').className;
    expect(cls).toContain('mt-1');
    expect(cls).toContain('accent-primary');
  });

  it('cannot be turned into another kind of input by a caller', () => {
    // `type` is spread AFTER the props in a naive implementation, so a stray
    // `type="text"` would silently produce a text field styled as a checkbox.
    renderWithProviders(
      // @ts-expect-error `type` is deliberately excluded from the props type
      <Checkbox aria-label="x" type="text" />
    );
    expect(screen.getByRole('checkbox')).toHaveAttribute('type', 'checkbox');
  });

  it('keeps the id it is given so <label htmlFor> stays wired', () => {
    renderWithProviders(
      <>
        <Checkbox id="remember-me" />
        <label htmlFor="remember-me">Remember me</label>
      </>
    );
    expect(screen.getByLabelText('Remember me')).toHaveAttribute('id', 'remember-me');
  });
});
