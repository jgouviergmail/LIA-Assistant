/**
 * AccountExportSettings — the GDPR full-account export section: status
 * badge, step-up-guarded request, download link on done, failure hints,
 * self-hiding when the instance has exports disabled (404), and the
 * SettingsSection accordion integration.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act } from 'react';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import userEvent from '@testing-library/user-event';
import { ApiError } from '@/lib/api-client';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, post } };
});
const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useStepUpGuard } = vi.hoisted(() => ({ useStepUpGuard: vi.fn() }));
vi.mock('@/hooks/useStepUpGuard', () => ({ useStepUpGuard }));
vi.mock('@/components/auth/StepUpDialog', () => ({
  StepUpDialog: ({ open }: { open: boolean }) => (open ? <div>step-up-open</div> : null),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { AccountExportSettings } from '../AccountExportSettings';

interface JobOver {
  status?: string;
  error_code?: string | null;
}

function job(over: JobOver = {}) {
  return {
    id: 'job-1',
    status: 'done',
    error_code: null,
    file_size_bytes: 1024,
    created_at: '2026-07-23T10:00:00Z',
    completed_at: '2026-07-23T10:05:00Z',
    expires_at: '2026-07-24T10:05:00Z',
    ...over,
  };
}

function queryHook(over: Record<string, unknown> = {}) {
  return {
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  post.mockResolvedValue({});
  useApiQuery.mockReturnValue(queryHook());
  useStepUpGuard.mockReturnValue({
    guard: (fn: () => Promise<unknown>) => fn(),
    stepUpOpen: false,
    onVerified: vi.fn(),
    onCancel: vi.fn(),
  });
});

describe('AccountExportSettings — states', () => {
  it('offers the request button with no prior job', () => {
    renderWithProviders(<AccountExportSettings />);
    expect(
      screen.getByRole('button', { name: 'settings.security.export.request' })
    ).toBeInTheDocument();
    expect(screen.queryByText(/status_/)).not.toBeInTheDocument();
  });

  it('shows the done badge and a same-origin download link', () => {
    // Same-origin contract: NEXT_PUBLIC_API_URL="" means relative /api/v1 URLs
    // through the BFF proxy (pinned by lib/__tests__/api-base-url-env.test.ts).
    // Stubbed EXPLICITLY rather than assumed absent — a developer shell (and the
    // lia-web-dev container) exports a real API origin, which made this the only
    // red in the suite there while CI stayed green by setting the var to "" at
    // the runner level. A test must state the condition it asserts.
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    try {
      useApiQuery.mockReturnValue(queryHook({ data: job() }));
      renderWithProviders(<AccountExportSettings />);

      expect(screen.getByText('settings.security.export.status_done')).toBeInTheDocument();
      const download = screen.getByRole('link', { name: 'settings.security.export.download' });
      expect(download).toHaveAttribute('href', '/api/v1/account/export/job-1/download');
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('targets the API origin when one is configured (never the frontend)', () => {
    // A relative /api/v1 href would hit the FRONTEND origin, which has no
    // such route — the download 404'd in the field (2026-07-23).
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.dev');
    try {
      useApiQuery.mockReturnValue(queryHook({ data: job() }));
      renderWithProviders(<AccountExportSettings />);

      expect(
        screen.getByRole('link', { name: 'settings.security.export.download' })
      ).toHaveAttribute('href', 'https://api.example.dev/api/v1/account/export/job-1/download');
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('disables the request button while a job is in flight', () => {
    useApiQuery.mockReturnValue(queryHook({ data: job({ status: 'running' }) }));
    renderWithProviders(<AccountExportSettings />);
    expect(
      screen.getByRole('button', { name: 'settings.security.export.in_progress' })
    ).toBeDisabled();
  });

  it('explains an export_too_large failure', () => {
    useApiQuery.mockReturnValue(
      queryHook({ data: job({ status: 'failed', error_code: 'export_too_large' }) })
    );
    renderWithProviders(<AccountExportSettings />);
    expect(screen.getByText('settings.security.export.too_large')).toBeInTheDocument();
  });

  it('hides itself when the instance has exports disabled (404)', async () => {
    let onError: ((e: Error) => void) | undefined;
    useApiQuery.mockImplementation((_url: string, options: { onError?: (e: Error) => void }) => {
      onError = options.onError;
      return queryHook();
    });
    const { container } = renderWithProviders(<AccountExportSettings />);
    // The hook reports the 404 after render, like the real fetch would.
    act(() => onError?.(new ApiError('Not found', 404)));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});

describe('AccountExportSettings — request flow', () => {
  it('requests through the step-up guard and refetches', async () => {
    const guard = vi.fn((fn: () => Promise<unknown>) => fn());
    useStepUpGuard.mockReturnValue({
      guard,
      stepUpOpen: false,
      onVerified: vi.fn(),
      onCancel: vi.fn(),
    });
    const hook = queryHook();
    useApiQuery.mockReturnValue(hook);
    const user = userEvent.setup();
    renderWithProviders(<AccountExportSettings />);

    await user.click(screen.getByRole('button', { name: 'settings.security.export.request' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith('/account/export'));
    expect(guard).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('settings.security.export.requested');
    await waitFor(() => expect(hook.refetch).toHaveBeenCalled());
  });

  it('surfaces a request failure without a success toast', async () => {
    post.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    renderWithProviders(<AccountExportSettings />);

    await user.click(screen.getByRole('button', { name: 'settings.security.export.request' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.security.export.error_generic')
    );
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe('AccountExportSettings — section shell', () => {
  it('renders itself as the open settings card the shell deep-links to', () => {
    const { container } = renderWithProviders(<AccountExportSettings />);

    // The anchor id is the deep-link contract (`?section=security-export`):
    // the pane polls it to tell an absent section from a slow one.
    expect(container.querySelector('#settings-section-security-export')).not.toBeNull();
    expect(
      screen.getByRole('heading', { name: 'settings.security.export.title' })
    ).toBeInTheDocument();
    // Body visible on mount — no disclosure step since ADR-227.
    expect(
      screen.getByRole('button', { name: 'settings.security.export.request' })
    ).toBeInTheDocument();
  });
});
