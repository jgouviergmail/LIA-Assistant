import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const { useAuth, post } = vi.hoisted(() => ({ useAuth: vi.fn(), post: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', () => ({ default: { post } }));

import { ApplicationHealthTokenCard } from '../ApplicationHealthTokenCard';

const identity = '11111111-1111-4111-8111-111111111111';
const secret = 'hm_private_browser_only';
function waiting(): ApplicationCommandStatus {
  const expires_at = new Date(Date.now() + 300000).toISOString();
  const interaction = { interaction_id: identity, kind: 'device' as const, expires_at };
  return {
    schema_version: 1,
    command_id: identity,
    operation_id: 'health_token.create',
    phase: 'waiting',
    expires_at,
    interaction,
    outcome: {
      success: false,
      phase: 'waiting',
      committed: false,
      no_op: false,
      values: {},
      error_code: null,
      interaction,
    },
  };
}
function result() {
  return {
    id: identity,
    token: secret,
    token_prefix: 'hm_public',
    label: 'Watch',
    created_at: new Date().toISOString(),
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'owner-one' } });
});

describe('Application health ingestion token', () => {
  it('requires a click, returns one private secret and never repeats issuance', async () => {
    post.mockResolvedValue(result());
    const checkResult = vi.fn();
    const { user } = renderWithProviders(
      <ApplicationHealthTokenCard status={waiting()} checkResult={checkResult} readError={null} />
    );
    expect(post).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'healthMetrics.tokens.generate' }));
    expect(screen.getByDisplayValue(secret)).toBeInTheDocument();
    expect(screen.getByDisplayValue(secret)).toHaveFocus();
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(`/application-commands/${identity}/health-token`, {});
    expect(
      screen.queryByRole('button', { name: 'healthMetrics.tokens.generate' })
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'common.close' }));
    expect(screen.queryByDisplayValue(secret)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'settings.application_tools.secure_check' })
    ).toHaveFocus();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('a lost response offers observation without a second creation', async () => {
    post.mockRejectedValue(new Error('offline'));
    const checkResult = vi.fn();
    const { user } = renderWithProviders(
      <ApplicationHealthTokenCard status={waiting()} checkResult={checkResult} readError={null} />
    );
    await user.click(screen.getByRole('button', { name: 'healthMetrics.tokens.generate' }));
    expect(
      screen.queryByRole('button', { name: 'healthMetrics.tokens.generate' })
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: 'settings.application_tools.secure_check' })
    );
    expect(checkResult).toHaveBeenCalledOnce();
    expect(post).toHaveBeenCalledOnce();
  });

  it('discards a late secret after an account switch and return', async () => {
    let resolve!: (value: ReturnType<typeof result>) => void;
    post.mockReturnValue(
      new Promise(done => {
        resolve = done;
      })
    );
    const status = waiting();
    const props = { status, checkResult: vi.fn(), readError: null };
    const { user, rerender } = renderWithProviders(<ApplicationHealthTokenCard {...props} />);
    await user.click(screen.getByRole('button', { name: 'healthMetrics.tokens.generate' }));
    useAuth.mockReturnValue({ user: { id: 'owner-two' } });
    rerender(<ApplicationHealthTokenCard {...props} />);
    useAuth.mockReturnValue({ user: { id: 'owner-one' } });
    rerender(<ApplicationHealthTokenCard {...props} />);
    await act(async () => {
      resolve(result());
    });
    expect(screen.queryByDisplayValue(secret)).not.toBeInTheDocument();
  });

  it('refuses expired approval and does not create on arrival', () => {
    const status = waiting();
    status.expires_at = new Date(Date.now() - 1000).toISOString();
    renderWithProviders(
      <ApplicationHealthTokenCard status={status} checkResult={vi.fn()} readError={null} />
    );
    expect(
      screen.queryByRole('button', { name: 'healthMetrics.tokens.generate' })
    ).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('does not display a malformed private response or retry it', async () => {
    post.mockResolvedValue({ ...result(), user_id: 'injected-authority' });
    const { user } = renderWithProviders(
      <ApplicationHealthTokenCard status={waiting()} checkResult={vi.fn()} readError={null} />
    );
    await user.click(screen.getByRole('button', { name: 'healthMetrics.tokens.generate' }));
    expect(screen.queryByDisplayValue(secret)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'healthMetrics.tokens.generate' })
    ).not.toBeInTheDocument();
  });
});
