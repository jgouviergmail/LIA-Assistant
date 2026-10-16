import { StrictMode } from 'react';
import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const { get, useAuth } = vi.hoisted(() => ({ get: vi.fn(), useAuth: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
import { PsycheLLMSummary } from '../PsycheLLMSummary';
beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue({ summary: 'Calm and focused.' });
});
describe('automatic owned psyche summary', () => {
  it('generates automatically once under StrictMode, with no dedicated button', async () => {
    renderWithProviders(
      <StrictMode>
        <PsycheLLMSummary lng="en" isOpen />
      </StrictMode>
    );
    expect(await screen.findByText('Calm and focused.')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith(
      '/psyche/summary',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
  it('does not generate while closed and generates once when visible', async () => {
    const { rerender } = renderWithProviders(<PsycheLLMSummary lng="en" isOpen={false} />);
    await act(async () => {});
    expect(get).not.toHaveBeenCalled();
    rerender(<PsycheLLMSummary lng="en" isOpen />);
    await screen.findByText('Calm and focused.');
    expect(get).toHaveBeenCalledTimes(1);
  });
  it('keeps the previous point visible while an automatic refresh is pending', async () => {
    const { rerender } = renderWithProviders(<PsycheLLMSummary lng="en" refreshKey={0} />);
    await screen.findByText('Calm and focused.');
    let finish: (value: { summary: string }) => void = () => {};
    get.mockImplementationOnce(
      () =>
        new Promise<{ summary: string }>(resolve => {
          finish = resolve;
        })
    );
    rerender(<PsycheLLMSummary lng="en" refreshKey={1} />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Calm and focused.')).toBeInTheDocument();
    await act(async () => finish({ summary: 'Updated automatically.' }));
    expect(await screen.findByText('Updated automatically.')).toBeInTheDocument();
  });
  it('shows an automatic generation error and retries only on the page refresh signal', async () => {
    get.mockRejectedValueOnce(new Error('model unavailable'));
    const { rerender } = renderWithProviders(<PsycheLLMSummary lng="en" refreshKey={0} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('psyche.summary.error');
    expect(get).toHaveBeenCalledTimes(1);
    rerender(<PsycheLLMSummary lng="en" refreshKey={1} />);
    expect(await screen.findByText('Calm and focused.')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });
  it('aborts a prior account generation and does not leak its response after returning', async () => {
    let finish: (value: { summary: string }) => void = () => {};
    get.mockImplementationOnce(
      () =>
        new Promise<{ summary: string }>(resolve => {
          finish = resolve;
        })
    );
    const { rerender } = renderWithProviders(<PsycheLLMSummary lng="en" />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    const signal: AbortSignal = get.mock.calls[0][1].signal;
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<PsycheLLMSummary lng="en" />);
    expect(await screen.findByText('Calm and focused.')).toBeInTheDocument();
    expect(signal.aborted).toBe(true);
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender(<PsycheLLMSummary lng="en" />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
    await act(async () => finish({ summary: 'Private stale point.' }));
    expect(screen.queryByText('Private stale point.')).not.toBeInTheDocument();
  });
  it('clears the old point and automatically regenerates after a confirmed reset', async () => {
    const { rerender } = renderWithProviders(<PsycheLLMSummary key="before" lng="en" />);
    await screen.findByText('Calm and focused.');
    get.mockResolvedValueOnce({ summary: 'After reset.' });
    rerender(<PsycheLLMSummary key="after" lng="en" />);
    expect(screen.queryByText('Calm and focused.')).not.toBeInTheDocument();
    expect(await screen.findByText('After reset.')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });
});

it('notifies its owner after generation so a newly initialized state can be observed without another model call', async () => {
  const onGenerated = vi.fn();
  renderWithProviders(<PsycheLLMSummary lng="en" onGenerated={onGenerated} />);
  await screen.findByText('Calm and focused.');
  expect(onGenerated).toHaveBeenCalledTimes(1);
  expect(get).toHaveBeenCalledTimes(1);
});
