import { beforeEach, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { CapabilityTransferDialog } from '../CapabilityTransferDialog';
import type { CapabilitySelection, CapabilityTransfer } from '@/lib/capability-sharing';

// A `t` that shows its interpolation, so the popup is seen naming what was
// shared with whom; one identity, as react-i18next memoizes it.
const i18n = vi.hoisted(() => ({
  t: (key: string, options?: Record<string, unknown>) =>
    options
      ? `${key}(${Object.entries(options)
          .map(([name, value]) => `${name}=${String(value)}`)
          .join(',')})`
      : key,
  i18n: { language: 'fr' },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => i18n }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  recipients: {
    loading: false,
    error: null as Error | null,
    data: [
      {
        id: '33333333-3333-4333-8333-333333333333',
        status: 'accepted',
        peer_display_name: 'Alice',
      },
    ],
  },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({
  useApplicationAccountQuery: () => mocks.recipients,
}));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, get: mocks.get, post: mocks.post } };
});

const source: CapabilitySelection = {
  id: '11111111-1111-4111-8111-111111111111',
  kind: 'skill',
  name: 'Example',
};
function receipt(overrides: Partial<CapabilityTransfer> = {}): CapabilityTransfer {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    kind: 'skill',
    name: 'Example',
    status: 'preparing',
    digest: 'a'.repeat(64),
    files: [{ path: 'SKILL.md', size: 50 }],
    omitted: ['.env'],
    requires_credentials: true,
    created_at: '2026-10-18T12:00:00Z',
    transferred_at: null,
    components: [],
    error_code: null,
    ...overrides,
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.recipients.loading = false;
  mocks.recipients.error = null;
  mocks.recipients.data = [
    { id: '33333333-3333-4333-8333-333333333333', status: 'accepted', peer_display_name: 'Alice' },
  ];
});

it('requires an explicit recipient, previews the inventory, then sends the bound digest', async () => {
  mocks.post
    .mockResolvedValueOnce(receipt())
    .mockResolvedValueOnce(
      receipt({ status: 'installed', transferred_at: '2026-10-18T12:00:01Z' })
    );
  const onClose = vi.fn();
  const user = userEvent.setup();
  renderWithProviders(<CapabilityTransferDialog source={source} onClose={onClose} />);
  expect(screen.getByRole('button', { name: 'settings.capability_share.preview' })).toBeDisabled();
  await user.click(screen.getByRole('radio', { name: 'Alice' }));
  await user.click(screen.getByRole('button', { name: 'settings.capability_share.preview' }));
  expect(await screen.findByText('SKILL.md')).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Example' })).toHaveFocus();
  expect(screen.getByText('.env')).toBeInTheDocument();
  expect(screen.getByText('settings.capability_share.credentials')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'settings.capability_share.send' }));
  await screen.findByText('settings.capability_share.status.installed');
  expect(screen.getByRole('region', { name: 'Example' })).toHaveFocus();
  expect(mocks.post.mock.calls[1][1]).toEqual({ expected_digest: receipt().digest });
  // The confirmation popup says what was shared with whom, then the dialog closes.
  expect(toast.success).toHaveBeenCalledWith(
    'settings.capability_share.sent.skill(name=Example,recipient=Alice)',
    { description: 'settings.capability_share.status.installed' }
  );
  expect(onClose).toHaveBeenCalledOnce();
  expect(toast.error).not.toHaveBeenCalled();
});

it('announces a refused send in a popup and keeps the dialog open to retry', async () => {
  mocks.post
    .mockResolvedValueOnce(receipt())
    .mockRejectedValueOnce(
      new ApiError('Too Many Requests', 429, { detail: 'peers_capability_quota_reached' })
    );
  mocks.get.mockRejectedValueOnce(new ApiError('Not Found', 404));
  const onClose = vi.fn();
  const user = userEvent.setup();
  renderWithProviders(<CapabilityTransferDialog source={source} onClose={onClose} />);
  await user.click(screen.getByRole('radio', { name: 'Alice' }));
  await user.click(screen.getByRole('button', { name: 'settings.capability_share.preview' }));
  await user.click(await screen.findByRole('button', { name: 'settings.capability_share.send' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'settings.capability_share.errors.quota'
  );
  expect(toast.error).toHaveBeenCalledWith(
    'settings.capability_share.not_sent(name=Example,recipient=Alice)',
    { description: 'settings.capability_share.errors.quota' }
  );
  expect(toast.success).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'settings.capability_share.send' })).toBeVisible();
});

it('shows each partial component and retries the same receipt rather than preparing another copy', async () => {
  mocks.post
    .mockResolvedValueOnce(receipt())
    .mockResolvedValueOnce(
      receipt({
        status: 'partial',
        components: [
          {
            kind: 'skill',
            key: 'done',
            resource_id: '44444444-4444-4444-8444-444444444444',
            installed: true,
            error_code: null,
          },
          {
            kind: 'mcp',
            key: 'missing',
            resource_id: null,
            installed: false,
            error_code: 'peers_capability_component_failed',
          },
        ],
      })
    )
    .mockResolvedValueOnce(
      receipt({ status: 'installed', transferred_at: '2026-10-18T12:00:01Z' })
    );
  const onClose = vi.fn();
  const user = userEvent.setup();
  renderWithProviders(<CapabilityTransferDialog source={source} onClose={onClose} />);
  await user.click(screen.getByRole('radio', { name: 'Alice' }));
  await user.click(screen.getByRole('button', { name: 'settings.capability_share.preview' }));
  await user.click(await screen.findByRole('button', { name: 'settings.capability_share.send' }));
  expect(await screen.findByText('missing')).toBeInTheDocument();
  expect(toast.warning).toHaveBeenCalledWith(
    'settings.capability_share.incomplete(name=Example,recipient=Alice)',
    { description: 'settings.capability_share.status.partial' }
  );
  expect(onClose).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'settings.capability_share.retry' }));
  await screen.findByText('settings.capability_share.status.installed');
  expect(mocks.post.mock.calls[1][0]).toBe(mocks.post.mock.calls[2][0]);
  expect(mocks.post.mock.calls.filter(([path]) => path.endsWith('/preview'))).toHaveLength(1);
  expect(toast.success).toHaveBeenCalledOnce();
  expect(onClose).toHaveBeenCalledOnce();
});

it('distinguishes failed recipient loading from a genuine empty list', async () => {
  mocks.recipients.error = new Error('offline');
  mocks.recipients.data = [];
  const { rerender } = renderWithProviders(
    <CapabilityTransferDialog source={source} onClose={vi.fn()} />
  );
  expect(screen.getByRole('alert')).toHaveTextContent('settings.peers.recipients.load_error');
  expect(screen.queryByText(/^settings\.peers\.recipients\.no_connection/)).not.toBeInTheDocument();
  mocks.recipients.error = null;
  rerender(<CapabilityTransferDialog source={source} onClose={vi.fn()} />);
  await waitFor(() =>
    expect(screen.getByText(/^settings\.peers\.recipients\.no_connection/)).toBeInTheDocument()
  );
});

it('keeps the send control focused and prevents a second submit during a pending request', async () => {
  let settle: ((value: CapabilityTransfer) => void) | undefined;
  mocks.post.mockResolvedValueOnce(receipt()).mockImplementationOnce(
    () =>
      new Promise<CapabilityTransfer>(resolve => {
        settle = resolve;
      })
  );
  const user = userEvent.setup();
  renderWithProviders(<CapabilityTransferDialog source={source} onClose={vi.fn()} />);
  await user.click(screen.getByRole('radio', { name: 'Alice' }));
  await user.click(screen.getByRole('button', { name: 'settings.capability_share.preview' }));
  const send = await screen.findByRole('button', { name: 'settings.capability_share.send' });
  await user.click(send);
  expect(send).toHaveFocus();
  expect(send).not.toBeDisabled();
  expect(send).toHaveAttribute('aria-disabled', 'true');
  await user.keyboard('{Enter}');
  expect(mocks.post).toHaveBeenCalledTimes(2);
  settle?.(receipt({ status: 'partial' }));
  await screen.findByText('settings.capability_share.status.partial');
});
