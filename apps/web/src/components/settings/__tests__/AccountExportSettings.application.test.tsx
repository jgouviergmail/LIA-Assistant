import { act, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ApiStepUpError } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';

const { get, post, useAuth, toast } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), useAuth: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, get, post } };
});
vi.mock('sonner', () => ({ toast }));
vi.mock('@/components/auth/StepUpDialog', () => ({
  StepUpDialog: ({ open, onVerified }: { open: boolean; onVerified: () => void }) =>
    open ? <button onClick={onVerified}>verify-export</button> : null,
}));
import { AccountExportSettings } from '../AccountExportSettings';

const job = { id: 'one-job', status: 'done', error_code: null, file_size_bytes: 1024,
  created_at: '2026-10-07T07:00:00Z', completed_at: '2026-10-07T07:01:00Z',
  expires_at: '2026-10-08T07:01:00Z', download_available: true };
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockResolvedValue(null);
  post.mockResolvedValue({});
});
const request = () => screen.getByRole('button', { name: 'settings.security.export.request' });

it('refreshes the owned export after assistant completion and ignores another account', async () => {
  get.mockResolvedValueOnce(job).mockResolvedValueOnce({ ...job, status: 'pending', download_available: false });
  renderWithProviders(<AccountExportSettings />);
  await screen.findByRole('link', { name: 'settings.security.export.download' });
  await act(async () => { publishApplicationResources('other', new Set(['account_export'])); });
  expect(get).toHaveBeenCalledTimes(1);
  await act(async () => { publishApplicationResources('one', new Set(['account_export'])); });
  await screen.findByRole('button', { name: 'settings.security.export.in_progress' });
  expect(screen.queryByRole('link', { name: 'settings.security.export.download' })).not.toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(2);
});

describe('Account export authenticated lifetime', () => {
  it('keeps keyboard focus on the busy action and ignores a second activation', async () => {
    post.mockImplementationOnce(() => new Promise(() => {}));
    renderWithProviders(<AccountExportSettings />);
    request().focus();
    fireEvent.click(request());
    await waitFor(() => expect(request()).toHaveAttribute('aria-disabled', 'true'));
    fireEvent.click(request());
    expect(request()).toHaveFocus();
    expect(post).toHaveBeenCalledTimes(1);
  });
  it('hides the previous archive until the new account read completes', async () => {
    get.mockResolvedValueOnce(job).mockImplementationOnce(() => new Promise(() => {}));
    const { rerender } = renderWithProviders(<AccountExportSettings />);
    await screen.findByRole('link', { name: 'settings.security.export.download' });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<AccountExportSettings />);
    expect(screen.queryByRole('link', { name: 'settings.security.export.download' })).toBeNull();
  });

  it('invalidates a parked step-up action across account changes and a return to the same account', async () => {
    post.mockRejectedValueOnce(new ApiStepUpError());
    const { rerender } = renderWithProviders(<AccountExportSettings />);
    fireEvent.click(request());
    const oldVerification = await screen.findByRole('button', { name: 'verify-export' });
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<AccountExportSettings />);
    expect(screen.queryByRole('button', { name: 'verify-export' })).toBeNull();
    useAuth.mockReturnValue({ user: { id: 'one' } });
    rerender(<AccountExportSettings />);
    fireEvent.click(oldVerification);
    await act(async () => {});
    expect(post).toHaveBeenCalledTimes(1);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it.each(['success', 'failure'])('discards a late %s without notifying or refreshing another account', async outcome => {
    let finish: ((value: unknown) => void) | undefined;
    let reject: ((reason: Error) => void) | undefined;
    post.mockImplementationOnce(() => new Promise((resolve, fail) => { finish = resolve; reject = fail; }));
    const { rerender } = renderWithProviders(<AccountExportSettings />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    fireEvent.click(request());
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender(<AccountExportSettings />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => {
      if (outcome === 'success') finish?.({});
      else reject?.(new Error('late failure'));
    });
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(get).toHaveBeenCalledTimes(2);
    expect(request()).toBeEnabled();
  });

  it('replays a verified request once for the unchanged account', async () => {
    post.mockRejectedValueOnce(new ApiStepUpError()).mockResolvedValueOnce({});
    renderWithProviders(<AccountExportSettings />);
    fireEvent.click(request());
    fireEvent.click(await screen.findByRole('button', { name: 'verify-export' }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledOnce());
    expect(post).toHaveBeenCalledTimes(2);
  });
});
