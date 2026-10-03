/**
 * The cosmos pages' pause control (WCAG 2.2.2): a native toggle button with a
 * stable translated name, `aria-pressed` carrying the state, usable from the
 * keyboard — and every instance on the page (header row, mobile menu) showing
 * the one state that lives on <html>.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { MotionToggle } from '../MotionToggle';

afterEach(() => {
  delete document.documentElement.dataset.motion;
  window.localStorage.clear();
});

describe('MotionToggle', () => {
  it('is a native button with a stable name, unpressed while the page moves', () => {
    render(<MotionToggle />);
    const button = screen.getByRole('button', { name: 'landing.motion.pause' });
    expect(button.tagName).toBe('BUTTON');
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });

  it('pauses the page and starts it again, the name never changing', () => {
    render(<MotionToggle />);
    const button = screen.getByRole('button', { name: 'landing.motion.pause' });

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(document.documentElement.dataset.motion).toBe('paused');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(document.documentElement.dataset.motion).toBeUndefined();
  });

  it('keeps every instance on the one state of the page', () => {
    render(
      <>
        <MotionToggle />
        <MotionToggle />
      </>
    );
    const [row, menu] = screen.getAllByRole('button', { name: 'landing.motion.pause' });

    fireEvent.click(row);
    expect(menu).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows its name next to the icon in a footer, with the same state', () => {
    render(<MotionToggle withLabel />);
    const button = screen.getByRole('button', { name: 'landing.motion.pause' });
    expect(button).toHaveTextContent('landing.motion.pause');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(document.documentElement.dataset.motion).toBe('paused');
  });

  it('activates from the keyboard', async () => {
    const user = userEvent.setup();
    render(<MotionToggle />);
    const button = screen.getByRole('button', { name: 'landing.motion.pause' });

    act(() => button.focus());
    await user.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });
});
