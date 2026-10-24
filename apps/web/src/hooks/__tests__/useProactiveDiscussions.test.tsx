import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
const { get, patch, post, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get, patch, post },
}));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
import {
  DISCUSSION_ACTIVITY_IDLE_POLL_MS,
  DISCUSSION_ACTIVITY_POLL_MS,
  useProactiveDiscussions,
} from '../useProactiveDiscussions';
import {
  DiscussionContext,
  DiscussionContextStatus,
} from '@/components/settings/DiscussionContext';
import type { DiscussionActivity, DiscussionSettings } from '@/types/proactive-discussions';

const initial: DiscussionSettings = {
  policy: {
    enabled: false,
    start_hour: 9,
    end_hour: 20,
    timezone: 'UTC',
    daily_max: 2,
    sources: [],
    sensitive_topics: [],
    forbidden_topics: [],
    paused_until: null,
    revision: 0,
  },
  sources: [{ key: 'portrait', operations: ['recent'], indivisible: true, dependencies: [] }],
  producer_enabled: false,
  budget_configured: false,
  pause_hours: 24,
};
const empty = {
  generation: 0,
  context_epoch: 7,
  forgotten_at: null,
  refresh_requested: false,
  items: [],
  total: 0,
  next_cursor: null,
  exclusions: [],
  exclusions_total: 0,
  exclusions_next_cursor: null,
  coverage: [],
};
const idle: DiscussionActivity = {
  rebuild: 'idle',
  obstacle: null,
  last_rebuild: null,
  last_update: null,
  last_run: null,
  budget: { configured: false, reached: null, resets_at: null },
  awaiting_reply: null,
};
let server: DiscussionSettings;
let activity: DiscussionActivity;
let context: typeof empty;
beforeEach(() => {
  vi.clearAllMocks();
  server = structuredClone(initial);
  activity = structuredClone(idle);
  context = structuredClone(empty);
  useAuth.mockReturnValue({ user: { id: 'owner-a' } });
  get.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith('/settings') ? server : path.endsWith('/activity') ? activity : context
    )
  );
});

it('keeps personal settings readable with the producer off and defers context reads until opened', async () => {
  const { result, rerender } = renderHook(({ open }) => useProactiveDiscussions(open), {
    initialProps: { open: false },
  });
  await waitFor(() => expect(result.current.settings.data).toEqual(initial));
  expect(get).toHaveBeenCalledTimes(1);
  rerender({ open: true });
  await waitFor(() => expect(result.current.context.data?.context_epoch).toBe(7));
});

it('writes one CAS patch during a pending click and accepts the current server result', async () => {
  let finish: ((value: DiscussionSettings) => void) | undefined;
  patch.mockImplementationOnce(
    () =>
      new Promise<DiscussionSettings>(resolve => {
        finish = resolve;
      })
  );
  const { result } = renderHook(() => useProactiveDiscussions(false));
  await waitFor(() => expect(result.current.settings.data).toEqual(initial));
  let pending: Promise<boolean> | undefined;
  act(() => {
    pending = result.current.update({ daily_max: null });
  });
  await act(async () => {
    await result.current.update({ enabled: true });
  });
  expect(patch).toHaveBeenCalledTimes(1);
  expect(patch).toHaveBeenCalledWith(
    '/proactive-discussions/settings',
    { expected_revision: 0, changes: { daily_max: null } },
    undefined
  );
  server = { ...initial, policy: { ...initial.policy, daily_max: null, revision: 1 } };
  await act(async () => {
    finish?.(server);
    await pending;
  });
  await waitFor(() => expect(result.current.settings.data?.policy.daily_max).toBeNull());
});

it('does not carry an old account response into the next account', async () => {
  let finish: ((value: DiscussionSettings) => void) | undefined;
  patch.mockImplementationOnce(
    () =>
      new Promise<DiscussionSettings>(resolve => {
        finish = resolve;
      })
  );
  const { result, rerender } = renderHook(() => useProactiveDiscussions(false));
  await waitFor(() => expect(result.current.settings.data).toEqual(initial));
  let pending: Promise<boolean> | undefined;
  act(() => {
    pending = result.current.update({ sources: ['portrait'] });
  });
  useAuth.mockReturnValue({ user: { id: 'owner-b' } });
  rerender();
  await waitFor(() => expect(result.current.settings.ownerId).toBe('owner-b'));
  await act(async () => {
    finish?.({ ...initial, policy: { ...initial.policy, sources: ['portrait'], revision: 1 } });
    await pending;
  });
  await waitFor(() => expect(result.current.settings.data?.policy.sources).toEqual([]));
  expect(result.current.saving).toBe(false);
});

it('sends the current forgetting epoch and treats a malformed acknowledgement as uncertain', async () => {
  post.mockResolvedValueOnce({ unexpected: 'not a context generation' });
  const { result } = renderHook(() => useProactiveDiscussions(true));
  await waitFor(() => expect(result.current.context.data).toEqual(empty));
  await act(async () => {
    expect(await result.current.contextAction('purge')).toBe(false);
  });
  expect(post).toHaveBeenCalledWith(
    '/proactive-discussions/context/purge',
    { expected_epoch: 7, expected_generation: empty.generation },
    undefined
  );
  expect(result.current.error).toBe(true);
  expect(result.current.context.data?.context_epoch).toBe(7);
});

it('purges only the generation explicitly reviewed even after a newer generation arrives', async () => {
  const { result } = renderHook(() => useProactiveDiscussions(true));
  await waitFor(() => expect(result.current.context.data).toEqual(empty));
  const reviewed = { expected_epoch: 7, expected_generation: 0 };
  await act(async () => {
    result.current.context.acceptData({ ...empty, generation: 4 });
  });
  post.mockResolvedValueOnce({ ...empty, context_epoch: 8, generation: 5 });
  await act(async () => {
    expect(await result.current.contextAction('purge', undefined, reviewed)).toBe(true);
  });
  expect(post).toHaveBeenLastCalledWith(
    '/proactive-discussions/context/purge',
    reviewed,
    undefined
  );
});

it('a purge preview performs no mutation signal and rejects a mismatched generation', async () => {
  const { result } = renderHook(() => useProactiveDiscussions(true));
  await waitFor(() => expect(result.current.context.data).toEqual(empty));
  post.mockResolvedValueOnce({
    context_epoch: 7,
    generation: 3,
    selected_count: 1,
    affected_count: 2,
  });
  let preview;
  await act(async () => {
    preview = await result.current.previewPurge(undefined, {
      expected_epoch: 7,
      expected_generation: 0,
    });
  });
  expect(preview).toBeUndefined();
  expect(result.current.context.data?.generation).toBe(0);
});

/** The two panels the settings page draws on one read: the status, then the data. */
function ContextPane() {
  const controls = useProactiveDiscussions(true);
  return (
    <>
      <DiscussionContextStatus lng="fr" controls={controls} />
      <DiscussionContext lng="fr" controls={controls} />
    </>
  );
}

it('keeps the rebuild in the « Context » panel and the data with its purge in the other', async () => {
  // Owner request 2026-10-21: the status and the data are two folded panels.
  activity = {
    ...idle,
    last_update: {
      kind: 'opening',
      state: 'completed',
      claimed_at: '2026-10-21T09:00:00Z',
      settled_at: '2026-10-21T09:01:00Z',
      reason: null,
      stats: null,
      usage: null,
    },
  };
  function StatusPane() {
    return <DiscussionContextStatus lng="fr" controls={useProactiveDiscussions(true)} />;
  }
  function DataPane() {
    return <DiscussionContext lng="fr" controls={useProactiveDiscussions(true)} />;
  }

  const status = render(<StatusPane />);
  expect(await screen.findByRole('button', { name: 'discussions.rebuild' })).toBeVisible();
  expect(await screen.findByText('discussions.activity.updated_at')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'discussions.purge_all' })).toBeNull();
  status.unmount();

  render(<DataPane />);
  expect(await screen.findByRole('button', { name: 'discussions.purge_all' })).toBeVisible();
  expect(screen.getByText('discussions.context_hint')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'discussions.rebuild' })).toBeNull();
  expect(screen.queryByText('discussions.activity.updated_at')).toBeNull();
});

it('explains a missing spending configuration after accepting a rebuild of empty context', async () => {
  server = {
    ...initial,
    producer_enabled: true,
    policy: { ...initial.policy, enabled: true, sources: ['portrait'] },
  };
  post.mockResolvedValueOnce({ ...empty, context_epoch: 8, refresh_requested: true });
  render(<ContextPane />);
  const rebuild = await screen.findByRole('button', { name: 'discussions.rebuild' });
  await userEvent.click(rebuild);
  await waitFor(() => expect(post).toHaveBeenCalledOnce());
  expect(post).toHaveBeenCalledWith(
    '/proactive-discussions/context/rebuild',
    { expected_epoch: 7 },
    undefined
  );
  expect(await screen.findByText('discussions.rebuild_budget_blocked')).toBeVisible();
  expect(screen.queryByText('discussions.rebuild_pending')).not.toBeInTheDocument();
  expect(screen.getByText('discussions.context_empty')).toBeVisible();
  expect(rebuild).toHaveFocus();
});

it('does not announce executable reconstruction when personal discussions are off', async () => {
  server = { ...initial, producer_enabled: true, budget_configured: true };
  post.mockResolvedValueOnce({ ...empty, context_epoch: 8, refresh_requested: true });
  render(<ContextPane />);
  await userEvent.click(await screen.findByRole('button', { name: 'discussions.rebuild' }));
  expect(await screen.findByText('discussions.rebuild_disabled')).toBeVisible();
  expect(screen.queryByText('discussions.rebuild_pending')).not.toBeInTheDocument();
});

it('keeps the rebuild busy while it runs, polls until it settles, then re-reads the context', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    server = {
      ...initial,
      producer_enabled: true,
      budget_configured: true,
      policy: { ...initial.policy, enabled: true, sources: ['portrait'] },
    };
    post.mockImplementationOnce(() => {
      activity = { ...idle, rebuild: 'running' };
      return Promise.resolve({ ...empty, context_epoch: 8, refresh_requested: true });
    });
    render(<ContextPane />);
    const rebuild = await screen.findByRole('button', { name: 'discussions.rebuild' });
    expect(rebuild).not.toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(rebuild);
    expect(await screen.findByText('discussions.rebuild_running')).toBeVisible();
    expect(rebuild).toHaveAttribute('aria-disabled', 'true');
    // A second click would fence off the run in flight: it sends nothing.
    await userEvent.click(rebuild);
    expect(post).toHaveBeenCalledOnce();
    expect(rebuild).toHaveFocus();
    const contextReads = () =>
      get.mock.calls.filter(([path]) => String(path).endsWith('/context')).length;
    const before = contextReads();
    activity = structuredClone(idle);
    context = { ...empty, context_epoch: 8, generation: 1 };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCUSSION_ACTIVITY_POLL_MS);
    });
    await waitFor(() => expect(contextReads()).toBeGreaterThan(before));
    await waitFor(() => expect(rebuild).not.toHaveAttribute('aria-disabled', 'true'));
    expect(screen.queryByText('discussions.rebuild_running')).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it('does not poll a requested rebuild the server says cannot start', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    server = {
      ...initial,
      producer_enabled: true,
      budget_configured: true,
      policy: { ...initial.policy, enabled: true, sources: ['portrait'] },
    };
    // Asked, but the person's controls cannot all be read: nothing starts until they act.
    activity = { ...idle, rebuild: 'requested', obstacle: 'controls_over_budget' };
    context = { ...empty, refresh_requested: true };
    render(<ContextPane />);
    expect(await screen.findByText('discussions.rebuild_controls_over_budget')).toBeVisible();
    const reads = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCUSSION_ACTIVITY_POLL_MS * 3);
    });
    expect(get.mock.calls.length).toBe(reads);
  } finally {
    vi.useRealTimers();
  }
});

it('does not poll while nothing is being rebuilt', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    render(<ContextPane />);
    await screen.findByRole('button', { name: 'discussions.rebuild' });
    const reads = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCUSSION_ACTIVITY_POLL_MS * 3);
    });
    expect(get.mock.calls.length).toBe(reads);
  } finally {
    vi.useRealTimers();
  }
});

it('re-reads the activity gently while the context is shown, and the context once a run updated it', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const run = {
      kind: 'opening' as const,
      state: 'skipped' as const,
      claimed_at: '2026-10-21T15:30:00Z',
      settled_at: '2026-10-21T15:31:00Z',
      reason: 'decision_skip',
      stats: null,
      usage: null,
    };
    activity = { ...idle, last_update: run, last_run: run };
    render(<ContextPane />);
    await screen.findByRole('button', { name: 'discussions.rebuild' });
    const reads = (suffix: string) =>
      get.mock.calls.filter(([path]) => String(path).endsWith(suffix)).length;
    const activityBefore = reads('/activity');
    const contextBefore = reads('/context');
    // An automatic run updates the context on its own schedule.
    const later = {
      ...run,
      claimed_at: '2026-10-21T15:32:00Z',
      settled_at: '2026-10-21T15:33:00Z',
    };
    activity = { ...idle, last_update: later, last_run: later };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCUSSION_ACTIVITY_IDLE_POLL_MS);
    });
    await waitFor(() => expect(reads('/activity')).toBeGreaterThan(activityBefore));
    await waitFor(() => expect(reads('/context')).toBeGreaterThan(contextBefore));
    // Nothing moved since: the next read leaves the context alone.
    const contextAfter = reads('/context');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCUSSION_ACTIVITY_IDLE_POLL_MS);
    });
    expect(reads('/context')).toBe(contextAfter);
  } finally {
    vi.useRealTimers();
  }
});
