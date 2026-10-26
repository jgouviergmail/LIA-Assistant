import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WorldPeerPanel } from '../WorldPeerPanel';

const port = vi.hoisted(() => ({ mutate: vi.fn(), isCurrent: () => true }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: port.mutate }) }));
vi.mock('@/hooks/useApplicationAccountLifetime', () => ({
  useApplicationAccountLifetime: () => ({ isCurrent: port.isCurrent }),
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const owner = '11111111-1111-4111-8111-111111111111';
const connection = '22222222-2222-4222-8222-222222222222';
const scope = () => ({ epoch: owner, controller: 'owned-controller-token' });
const page = {
  peers: [{ connection, name: 'Known person', presence: 'offline' }],
  next_cursor: null,
};

beforeEach(() => {
  port.mutate.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it.each(['online', 'home', 'away', 'offline'] as const)(
  'announces the coarse %s state without relying on colour',
  async presence => {
    port.mutate.mockResolvedValue({ ...page, peers: [{ ...page.peers[0], presence }] });
    render(<WorldPeerPanel lng="en" ownerId={owner} getScope={scope} onCompose={vi.fn()} />);
    await screen.findByRole('heading', { name: 'Known person' });
    expect(screen.getByText('world.peers.' + presence)).toBeVisible();
    expect(document.querySelector('[data-world-peer-presence]')).toHaveAttribute(
      'data-world-peer-presence',
      presence
    );
  }
);

it('refreshes presence without overlapping requests or dropping focus and keeps failures explicit', async () => {
  vi.useFakeTimers();
  let fail: (error: Error) => void = () => {};
  port.mutate.mockResolvedValueOnce(page).mockImplementationOnce(
    () =>
      new Promise((_resolve, reject) => {
        fail = reject;
      })
  );
  const view = render(
    <WorldPeerPanel lng="en" ownerId={owner} getScope={scope} onCompose={vi.fn()} />
  );
  await act(async () => {});
  const relay = screen.getByRole('button', { name: 'world.peers.relay' });
  relay.focus();
  await act(async () => vi.advanceTimersByTimeAsync(40000));
  expect(port.mutate).toHaveBeenCalledTimes(2);
  expect(relay).toHaveFocus();
  await act(async () => fail(new Error('network unavailable')));
  expect(screen.getByRole('heading', { name: 'Known person' })).toBeVisible();
  expect(screen.getByText('world.peers.presence_unavailable')).toBeVisible();
  expect(relay).toHaveFocus();
  view.unmount();
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(port.mutate).toHaveBeenCalledTimes(2);
});

it('preserves existing rows and keyboard focus while a presence-only refresh is pending', async () => {
  let finish: (value: unknown) => void = () => {};
  port.mutate.mockResolvedValueOnce(page).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      })
  );
  const props = { lng: 'en' as const, ownerId: owner, getScope: scope, onCompose: vi.fn() };
  const view = render(<WorldPeerPanel {...props} presenceKey="one" />);
  await screen.findByRole('heading', { name: 'Known person' });
  const action = screen.getByRole('button', { name: 'world.peers.relay' });
  action.focus();
  view.rerender(<WorldPeerPanel {...props} presenceKey="two" />);
  await waitFor(() => expect(port.mutate).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('heading', { name: 'Known person' })).toBeVisible();
  expect(action).toHaveFocus();
  expect(screen.getByRole('heading').closest('[aria-busy]')).toHaveAttribute('aria-busy', 'true');
  await act(async () => finish(page));
  expect(screen.getByRole('button', { name: 'world.peers.relay' })).toBe(action);
  expect(action).toHaveFocus();
  expect(screen.getByRole('heading').closest('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
  view.unmount();
});

it('hides an old account immediately and ignores the aborted old response', async () => {
  let finish: (value: unknown) => void = () => {};
  const signals: AbortSignal[] = [];
  port.mutate.mockImplementation((_url, _body, options: { signal: AbortSignal }) => {
    signals.push(options.signal);
    return new Promise(resolve => {
      finish = resolve;
    });
  });
  const props = { lng: 'en' as const, getScope: scope, onCompose: vi.fn() };
  const view = render(<WorldPeerPanel {...props} ownerId={owner} />);
  await waitFor(() => expect(port.mutate).toHaveBeenCalledTimes(1));
  const oldFinish = finish;
  view.rerender(<WorldPeerPanel {...props} ownerId={connection} />);
  expect(signals[0].aborted).toBe(true);
  await act(async () => oldFinish(page));
  expect(screen.queryByText('Known person')).not.toBeInTheDocument();
  view.unmount();
  expect(signals.every(signal => signal.aborted)).toBe(true);
});

it('pauses hidden refreshes and recovers from a malformed presence response without losing the row', async () => {
  vi.useFakeTimers();
  let hidden = true;
  vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  port.mutate
    .mockResolvedValueOnce(page)
    .mockResolvedValueOnce({ ...page, peers: [{ ...page.peers[0], presence: 'invented' }] })
    .mockResolvedValue({ ...page, peers: [{ ...page.peers[0], presence: 'home' }] });
  const view = render(
    <WorldPeerPanel lng="en" ownerId={owner} getScope={scope} onCompose={vi.fn()} />
  );
  await act(async () => vi.advanceTimersByTimeAsync(30000));
  expect(port.mutate).not.toHaveBeenCalled();
  hidden = false;
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  expect(screen.getByText('world.peers.offline')).toBeVisible();
  const relay = screen.getByRole('button', { name: 'world.peers.relay' });
  relay.focus();
  await act(async () => vi.advanceTimersByTimeAsync(10000));
  expect(screen.getByText('world.peers.presence_unavailable')).toBeVisible();
  expect(relay).toHaveFocus();
  hidden = true;
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  await act(async () => vi.advanceTimersByTimeAsync(30000));
  expect(port.mutate).toHaveBeenCalledTimes(2);
  hidden = false;
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  expect(screen.getByText('world.peers.home')).toBeVisible();
  expect(screen.queryByText('world.peers.presence_unavailable')).not.toBeInTheDocument();
  expect(relay).toHaveFocus();
  view.unmount();
});
