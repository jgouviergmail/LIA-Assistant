/**
 * ScrollToBottomButton (UXR Lot 3, A3) — the floating return affordance:
 * follow mode (icon-only, named), historyView mode (labelled "return to the
 * present", QW-2 semantics), and the "new responses" badge.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ScrollToBottomButton } from '../ScrollToBottomButton';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) =>
      opts?.count !== undefined ? `${key}:${opts.count}` : key,
  }),
}));

describe('ScrollToBottomButton', () => {
  it('is a named native button in follow mode (icon-only)', () => {
    render(<ScrollToBottomButton historyView={false} count={0} onClick={vi.fn()} />);
    const button = screen.getByRole('button', { name: 'chat.scroll.to_bottom' });
    expect(button).toBeInTheDocument();
    expect(button.textContent).toBe(''); // icon-only, the name is programmatic
  });

  it('labels the return-to-present action while viewing history', () => {
    render(<ScrollToBottomButton historyView count={0} onClick={vi.fn()} />);
    const button = screen.getByRole('button', { name: 'chat.scroll.return_to_present' });
    expect(button).toHaveTextContent('chat.scroll.return_to_present');
  });

  it('shows the new-responses badge only when something arrived', () => {
    const { rerender } = render(
      <ScrollToBottomButton historyView={false} count={0} onClick={vi.fn()} />
    );
    expect(screen.queryByText(/new_responses/)).not.toBeInTheDocument();

    rerender(<ScrollToBottomButton historyView={false} count={2} onClick={vi.fn()} />);
    expect(screen.getByText('chat.scroll.new_responses:2')).toBeInTheDocument();
  });

  it('fires the click handler', () => {
    const onClick = vi.fn();
    render(<ScrollToBottomButton historyView={false} count={0} onClick={onClick} />);
    fireEvent.click(screen.getByRole('button', { name: 'chat.scroll.to_bottom' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
