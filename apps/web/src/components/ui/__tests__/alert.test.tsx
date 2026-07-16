/**
 * Alert — the ARIA live region, the dismiss affordances (button, Escape),
 * auto-dismiss timing and the compound sub-components.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';

import { renderWithProviders, screen, fireEvent, act } from '@/__tests__/test-utils';
import { Alert } from '../alert';

describe('Alert — structure', () => {
  it('renders an assertive-polite alert region with its content', () => {
    renderWithProviders(<Alert variant="info">Heads up</Alert>);
    const region = screen.getByRole('alert');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveTextContent('Heads up');
  });

  it('renders the compound icon, title and description sub-components', () => {
    renderWithProviders(
      <Alert variant="success">
        <Alert.Icon variant="success" />
        <Alert.Content>
          <Alert.Title>Done</Alert.Title>
          <Alert.Description>Saved successfully</Alert.Description>
        </Alert.Content>
      </Alert>
    );
    expect(screen.getByRole('heading', { name: 'Done' })).toBeInTheDocument();
    expect(screen.getByText('Saved successfully')).toBeInTheDocument();
  });
});

describe('Alert — dismiss affordances', () => {
  it('shows no dismiss button unless dismissible', () => {
    renderWithProviders(<Alert variant="warning">msg</Alert>);
    expect(screen.queryByRole('button', { name: 'Dismiss notification' })).not.toBeInTheDocument();
  });

  it('dismisses on button click, hiding itself and notifying the caller', async () => {
    const onDismiss = vi.fn();
    const { user } = renderWithProviders(
      <Alert variant="error" dismissible onDismiss={onDismiss}>
        msg
      </Alert>
    );
    await user.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('dismisses on Escape when dismissible', () => {
    const onDismiss = vi.fn();
    renderWithProviders(
      <Alert variant="info" dismissible onDismiss={onDismiss}>
        msg
      </Alert>
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('ignores Escape when not dismissible', () => {
    const onDismiss = vi.fn();
    renderWithProviders(
      <Alert variant="info" onDismiss={onDismiss}>
        msg
      </Alert>
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onDismiss).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

describe('Alert — auto-dismiss', () => {
  afterEach(() => vi.useRealTimers());

  it('auto-dismisses after the configured delay', () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    renderWithProviders(
      <Alert variant="success" autoDismiss={3000} onDismiss={onDismiss}>
        msg
      </Alert>
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not auto-dismiss before the delay elapses', () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    renderWithProviders(
      <Alert variant="success" autoDismiss={3000} onDismiss={onDismiss}>
        msg
      </Alert>
    );
    act(() => {
      vi.advanceTimersByTime(2999);
    });
    expect(onDismiss).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
