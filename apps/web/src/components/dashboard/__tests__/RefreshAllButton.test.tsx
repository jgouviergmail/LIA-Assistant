import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { RefreshAllButton } from '../RefreshAllButton';

describe('RefreshAllButton', () => {
  it('retains focus while pending and only runs an explicit available refresh', () => {
    const refresh = vi.fn();
    const { rerender } = renderWithProviders(
      <RefreshAllButton onClick={refresh} isRefreshing={false} />
    );
    const button = screen.getByRole('button', { name: 'dashboard.briefing.refresh_all' });
    button.focus();
    fireEvent.click(button);
    expect(refresh).toHaveBeenCalledTimes(1);
    rerender(<RefreshAllButton onClick={refresh} isRefreshing />);
    expect(button).toHaveFocus();
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(button);
    expect(refresh).toHaveBeenCalledTimes(1);
    rerender(<RefreshAllButton onClick={refresh} isRefreshing={false} />);
    fireEvent.click(button);
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
