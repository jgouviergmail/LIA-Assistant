import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import type { BriefingResponse, CardSection, SectionData } from '@/types/briefing';
import { Activity, type ReactNode } from 'react';

const { get, post, useAuth } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  useAuth: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { get, post } };
});
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
import { useBriefing } from '../useBriefing';

function section<T extends SectionData>(data: T): CardSection<T> {
  return {
    status: 'ok',
    data,
    generated_at: '2026-10-15T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

function emptySection(): Omit<CardSection, 'data'> & { data: null } {
  return { ...section(null), status: 'not_configured', data: null };
}

function response(id: string | null = 'saved'): BriefingResponse {
  return {
    windows: {
      birthdays_horizon_days: 7,
      health_window_days: 14,
      agenda_lookahead_hours: 24,
      tasks_horizon_days: 7,
      weather_forecast_days: 5,
    },
    greeting: { text: 'Good morning', generated_at: '2026-10-15T08:00:00Z', usage: null },
    synthesis: { text: 'Your daily point', generated_at: '2026-10-15T08:00:00Z', usage: null },
    cards: {
      weather: emptySection(),
      agenda: emptySection(),
      mails: emptySection(),
      birthdays: emptySection(),
      reminders: section({
        items: id ? [{ id, content: id, trigger_at_local: '09:00' }] : [],
      }),
      health: emptySection(),
      for_you: section({
        open_loops: id
          ? [
              {
                id,
                subject: id,
                counterparty: null,
                direction: 'user_owes',
                due_hint: null,
                days_open: 1,
              },
            ]
          : [],
        recent_automations: [],
        next_automation: null,
      }),
      tasks: emptySection(),
      documents: emptySection(),
      workboard: emptySection(),
    },
  };
}

const cards = response();
function smsResponse(
  body = 'WITHDRAWN_PRIVATE_SMS',
  id = '10000000-0000-4000-8000-000000000001'
): BriefingResponse {
  const initial = response();
  initial.cards.sms = section({
    timezone: 'Europe/Paris',
    total: 1,
    window_total: 1,
    window_start: '2026-10-19T08:00:00Z',
    as_of: '2026-10-20T08:00:00Z',
    latest_at: null,
    items: [
      {
        id,
        sender: 'Alice',
        display_name: 'Alice',
        received_at: '2026-10-20T07:00:00Z',
        date_kind: 'received',
        body_excerpt: body,
        body_truncated: false,
      },
    ],
  });
  return initial;
}
beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  get.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith('/cards') ? cards : { greeting: cards.greeting, synthesis: cards.synthesis }
    )
  );
});

async function ready() {
  const hook = renderHook(() => useBriefing());
  await waitFor(() => expect(hook.result.current.cards).toEqual(cards.cards));
  return hook;
}

describe('briefing reads and recovery', () => {
  it('rejects a pre-suspension POST after Activity restores the same enabled hook instance', async () => {
    let visible = true;
    const wrapper = ({ children }: { children: ReactNode }) => (
      <Activity mode={visible ? 'visible' : 'hidden'}>{children}</Activity>
    );
    const pending = Promise.withResolvers<BriefingResponse>();
    post.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(() => useBriefing(), { wrapper });
    await waitFor(() => expect(result.current.text).toBeDefined());
    let refresh = Promise.resolve();
    act(() => {
      refresh = result.current.refetchSection('all');
    });
    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    visible = false;
    rerender();
    await act(async () => {});
    visible = true;
    rerender();
    await waitFor(() =>
      expect(get.mock.calls.filter(call => call[0].endsWith('/cards'))).toHaveLength(2)
    );
    await act(async () => {
      pending.resolve(response('obsolete-after-activity'));
      await refresh;
    });
    expect(result.current.cards?.reminders?.data?.items[0].id).toBe('saved');
  });
  it('withdraws SMS-derived text while suspended without fetching or restoring it on resume', async () => {
    const initial = smsResponse();
    get.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith('/cards') ? initial : initial)
    );
    const { result, rerender } = renderHook(({ enabled }) => useBriefing(enabled), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(result.current.text).toBeDefined());
    rerender({ enabled: false });
    act(() => publishApplicationResources('one', new Set(['sms'])));
    expect(result.current.text).toBeUndefined();
    expect(result.current.cards?.sms?.data?.items).toEqual([]);
    expect(post).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() =>
      expect(get.mock.calls.filter(call => call[0].endsWith('/cards'))).toHaveLength(2)
    );
    expect(result.current.text).toBeUndefined();
    expect(get.mock.calls.filter(call => call[0].endsWith('/synthesis'))).toHaveLength(1);
  });
  it('pauses both reads and resumes cards without purchasing another initial synthesis', async () => {
    post.mockResolvedValue(response('fresh-after-suspension'));
    const { result, rerender } = renderHook(({ enabled }) => useBriefing(enabled), {
      initialProps: { enabled: false },
    });
    await act(async () => {});
    expect(get).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.text?.greeting.text).toBe('Good morning'));
    rerender({ enabled: false });
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    expect(post).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() =>
      expect(get.mock.calls.filter(call => call[0].endsWith('/cards'))).toHaveLength(2)
    );
    expect(get.mock.calls.filter(call => call[0].endsWith('/synthesis'))).toHaveLength(1);
    expect(result.current.text?.greeting.text).toBe('Good morning');
    await waitFor(() =>
      expect(result.current.cards?.reminders?.data?.items[0].id).toBe('fresh-after-suspension')
    );
    expect(post.mock.calls.map(call => call[0])).toEqual(['/briefing/refresh-cards']);
  });

  it('aborts a suspended manual refresh and rejects its late result and retained retry', async () => {
    const pending = Promise.withResolvers<BriefingResponse>();
    post.mockReturnValue(pending.promise);
    const { result, rerender } = renderHook(({ enabled }) => useBriefing(enabled), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(result.current.text).toBeDefined());
    const retained = result.current.refetchSection;
    let refresh: Promise<void>;
    act(() => {
      refresh = retained('all');
    });
    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    const signal: AbortSignal = post.mock.calls[0][2].signal;
    rerender({ enabled: false });
    expect(signal.aborted).toBe(true);
    rerender({ enabled: true });
    await act(async () => {
      pending.resolve(response('obsolete'));
      await refresh;
      await retained('all');
    });
    expect(result.current.cards?.reminders?.data?.items[0].id).toBe('saved');
    expect(post).toHaveBeenCalledOnce();
  });

  it('does not automatically retry a paid initial request aborted on suspension', async () => {
    const pending = Promise.withResolvers<BriefingResponse>();
    get.mockImplementation((path: string) =>
      path.endsWith('/cards') ? Promise.resolve(cards) : pending.promise
    );
    const { result, rerender } = renderHook(({ enabled }) => useBriefing(enabled), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    const signal: AbortSignal = get.mock.calls.find(call => call[0].endsWith('/synthesis'))![1]
      .signal;
    rerender({ enabled: false });
    expect(signal.aborted).toBe(true);
    rerender({ enabled: true });
    await act(async () => pending.resolve(cards));
    expect(result.current.text).toBeUndefined();
    expect(get.mock.calls.filter(call => call[0].endsWith('/synthesis'))).toHaveLength(1);
    expect(result.current.textLoading).toBe(false);
    expect(result.current.textUnavailable).toBe(true);
    await act(async () => result.current.refetchAll());
    expect(get.mock.calls.filter(call => call[0].endsWith('/synthesis'))).toHaveLength(2);
  });
  it('withdraws SMS previews immediately and keeps them hidden when source rereading fails', async () => {
    const initial = smsResponse();
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/cards')
          ? initial
          : { greeting: initial.greeting, synthesis: initial.synthesis }
      )
    );
    const pendingRead = Promise.withResolvers<BriefingResponse>();
    post.mockReturnValue(pendingRead.promise);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.cards?.sms?.data?.items).toHaveLength(1));
    act(() => publishApplicationResources('one', new Set(['sms'])));
    expect(result.current.cards?.sms?.data?.items).toEqual([]);
    expect(result.current.cards?.for_you).toEqual(initial.cards.for_you);
    await act(async () => pendingRead.reject(new Error('offline')));
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.cards?.sms?.data?.items).toEqual([]);
  });

  it('masks a stale first-load response until the post-event SMS read completes', async () => {
    const first = Promise.withResolvers<BriefingResponse>();
    const fresh = Promise.withResolvers<BriefingResponse>();
    get.mockImplementation((path: string) =>
      path.endsWith('/cards')
        ? first.promise
        : Promise.resolve({ greeting: cards.greeting, synthesis: cards.synthesis })
    );
    post.mockReturnValue(fresh.promise);
    const { result } = renderHook(() => useBriefing());
    act(() => publishApplicationResources('one', new Set(['sms'])));
    await act(async () => first.resolve(smsResponse()));
    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    expect(result.current.cards?.sms?.data?.items).toEqual([]);
    await act(async () =>
      fresh.resolve(smsResponse('FRESH_SMS', '10000000-0000-4000-8000-000000000002'))
    );
    await waitFor(() =>
      expect(result.current.cards?.sms?.data?.items?.[0].body_excerpt).toBe('FRESH_SMS')
    );
  });

  it('rereads only SMS on a matching account event without regenerating paid text', async () => {
    const { result } = await ready();
    const previous = result.current.text;
    const fresh = response();
    fresh.cards.sms = section({
      timezone: 'Europe/Paris',
      total: 137,
      window_total: 5,
      window_start: '2026-10-19T08:00:00Z',
      as_of: '2026-10-20T08:00:00Z',
      latest_at: '2026-10-20T07:55:00Z',
    });
    post.mockResolvedValue(fresh);
    act(() => publishApplicationResources('foreign', new Set(['sms'])));
    expect(post).not.toHaveBeenCalled();
    expect(result.current.text).toBe(previous);
    act(() => publishApplicationResources('one', new Set(['sms'])));
    await waitFor(() => expect(result.current.cards?.sms?.data?.total).toBe(137));
    expect(post.mock.calls.map(call => call[0])).toEqual(['/briefing/refresh-cards']);
    expect(post.mock.calls[0][1]).toEqual({ sections: ['sms'] });
    expect(result.current.text).toBeUndefined();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('cannot reinstall an old initial synthesis after an SMS invalidation', async () => {
    let completeText: ((value: unknown) => void) | undefined;
    get.mockImplementation((path: string) =>
      path.endsWith('/cards')
        ? Promise.resolve(cards)
        : new Promise(resolve => {
            completeText = resolve;
          })
    );
    post.mockResolvedValue(cards);
    const hook = renderHook(() => useBriefing());
    await waitFor(() => expect(hook.result.current.cards).toEqual(cards.cards));
    act(() => publishApplicationResources('one', new Set(['sms'])));
    await act(async () =>
      completeText?.({
        greeting: { ...cards.greeting, text: 'PRIVATE_OLD_SMS' },
        synthesis: cards.synthesis,
      })
    );
    expect(hook.result.current.text).toBeUndefined();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('cannot reinstall a paid manual synthesis after an SMS invalidation', async () => {
    const { result } = await ready();
    let complete: ((value: BriefingResponse) => void) | undefined;
    post.mockImplementation((path: string) =>
      path === '/briefing/refresh'
        ? new Promise(resolve => {
            complete = resolve;
          })
        : Promise.resolve(cards)
    );
    let refresh: Promise<void> | undefined;
    act(() => {
      refresh = result.current.refetchSection('all');
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    act(() => publishApplicationResources('one', new Set(['sms'])));
    const old = response();
    old.synthesis = {
      generated_at: old.greeting.generated_at,
      usage: null,
      text: 'PRIVATE_OLD_SMS',
    };
    await act(async () => {
      complete?.(old);
      await refresh;
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(result.current.text).toBeUndefined();
    expect(post.mock.calls.map(call => call[0])).toEqual([
      '/briefing/refresh',
      '/briefing/refresh-cards',
    ]);
  });

  it('forces only visible cards for a committed reminder change without buying text', async () => {
    const { result } = await ready();
    post.mockResolvedValue(response(null));
    act(() => publishApplicationResources('foreign', new Set(['reminders'])));
    expect(post).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    await waitFor(() => expect(result.current.cards?.reminders.data?.items).toEqual([]));
    expect(post.mock.calls.map(call => call[0])).toEqual(['/briefing/refresh-cards']);
    expect(post.mock.calls[0][1]).toEqual({ sections: ['reminders'] });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('hides old data and rejects parked refreshes after switching accounts', async () => {
    const { result, rerender } = await ready();
    const retired = result.current.refetchSection;
    get.mockReturnValue(new Promise(() => {}));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    rerender();
    expect(result.current.cards).toBeUndefined();
    expect(result.current.text).toBeUndefined();
    await act(async () => retired('reminders'));
    expect(post).not.toHaveBeenCalled();
  });

  it('deduplicates a global double press before React marks the control busy', async () => {
    const { result } = await ready();
    const build = Promise.withResolvers<BriefingResponse>();
    post.mockReturnValue(build.promise);
    const refreshes: Promise<void>[] = [];
    act(() => {
      refreshes.push(result.current.refetchSection('all'));
      refreshes.push(result.current.refetchSection('all'));
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await act(async () => {
      build.resolve(cards);
      await Promise.all(refreshes);
    });
    expect(post.mock.calls[0][0]).toBe('/briefing/refresh');
    expect(result.current.refreshingSections.size).toBe(0);
  });

  it('reports a failed cards refresh, retains data and permits explicit recovery', async () => {
    const { result } = await ready();
    post.mockRejectedValueOnce(new Error('offline'));
    await act(async () => result.current.refetchSection('reminders'));
    expect(result.current.error?.message).toBe('offline');
    expect(result.current.cards).toEqual(cards.cards);
    post.mockResolvedValueOnce(response('recovered'));
    await act(async () => result.current.refetchSection('reminders'));
    expect(result.current.error).toBeNull();
    expect(result.current.cards?.reminders.data?.items[0]?.id).toBe('recovered');
  });

  it('clears the recovered initial cards error and exposes a later failure', async () => {
    get.mockImplementation((path: string) =>
      path.endsWith('/cards')
        ? Promise.reject(new Error('initial offline'))
        : Promise.resolve(cards)
    );
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.error?.message).toBe('initial offline'));
    post.mockResolvedValueOnce(response('recovered'));
    await act(async () => result.current.refetchSection('reminders'));
    expect(result.current.error).toBeNull();
    expect(result.current.cards?.reminders.data?.items[0]?.id).toBe('recovered');
    get.mockImplementation((path: string) =>
      path.endsWith('/cards') ? Promise.reject(new Error('future offline')) : Promise.resolve(cards)
    );
    await act(async () => result.current.refetchAll());
    expect(result.current.error?.message).toBe('future offline');
    expect(post.mock.calls.every(call => call[0] === '/briefing/refresh-cards')).toBe(true);
  });

  it('clears both failed initial reads after successful explicit global generation', async () => {
    get.mockRejectedValue(new Error('initial offline'));
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.loading).toBe(false));
    post.mockResolvedValueOnce(response('recovered'));
    await act(async () => result.current.refetchSection('all'));
    expect(result.current.error).toBeNull();
    expect(result.current.cards?.reminders.data?.items[0]?.id).toBe('recovered');
    expect(result.current.text?.greeting.text).toBe('Good morning');
  });

  it('keeps an unrelated synthesis failure visible after cards-only recovery', async () => {
    get.mockImplementation((path: string) =>
      path.endsWith('/cards') ? Promise.resolve(cards) : Promise.reject(new Error('text offline'))
    );
    const { result } = await ready();
    await waitFor(() => expect(result.current.error?.message).toBe('text offline'));
    post.mockResolvedValueOnce(response(null));
    await act(async () => result.current.refetchSection('reminders'));
    expect(result.current.error?.message).toBe('text offline');
  });
});

describe('briefing server build ordering', () => {
  it('retains both explicit scopes when distinct cards refresh together', async () => {
    const { result } = await ready();
    const first = Promise.withResolvers<BriefingResponse>();
    const combined = response('combined');
    combined.cards.agenda = section({
      events: [{ title: 'Fresh agenda', start_local: '10:00', end_local: null, location: null }],
    });
    combined.cards.mails = section({ items: [], total_unread_today: 3 });
    post.mockReturnValueOnce(first.promise).mockResolvedValueOnce(combined);
    const refreshes: Promise<void>[] = [];
    act(() => {
      refreshes.push(result.current.refetchSection('agenda'));
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    act(() => {
      refreshes.push(result.current.refetchSection('mails'));
    });
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => {
      first.resolve(response('first'));
      await Promise.all(refreshes);
    });
    expect(post.mock.calls[1][1]).toEqual({ sections: ['agenda', 'mails'] });
    expect(result.current.cards?.agenda.data?.events[0]?.title).toBe('Fresh agenda');
    expect(result.current.cards?.mails.data?.total_unread_today).toBe(3);
    expect(post.mock.calls.every(call => call[0] === '/briefing/refresh-cards')).toBe(true);
  });

  it('rereads after a shared build finishes instead of joining its pre-mutation snapshot', async () => {
    const { result } = await ready();
    const build = Promise.withResolvers<BriefingResponse>();
    let building = true;
    // Matching force keys return the SAME server snapshot until the build ends.
    post.mockImplementation(() => (building ? build.promise : Promise.resolve(response(null))));
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => {
      building = false;
      build.resolve(response('cancelled-during-build'));
    });
    await waitFor(() => expect(result.current.cards?.reminders.data?.items).toEqual([]));
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls.every(call => call[0] === '/briefing/refresh-cards')).toBe(true);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it.each(['all', 'reminders'] as const)(
    'drains mutation invalidation after a pending %s refresh',
    async scope => {
      const { result } = await ready();
      const old = Promise.withResolvers<BriefingResponse>();
      post.mockReturnValueOnce(old.promise).mockResolvedValueOnce(response(null));
      const requests: Promise<void>[] = [];
      act(() => {
        requests.push(result.current.refetchSection(scope));
      });
      await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
      act(() => {
        requests.push(result.current.invalidateSection('reminders'));
      });
      expect(post).toHaveBeenCalledTimes(1);
      await act(async () => {
        old.resolve(cards);
        await Promise.all(requests);
      });
      expect(result.current.cards?.reminders.data?.items).toEqual([]);
      expect(post.mock.calls.filter(call => call[0] === '/briefing/refresh')).toHaveLength(
        scope === 'all' ? 1 : 0
      );
      expect(get).toHaveBeenCalledTimes(2);
    }
  );

  it('carries concurrent reminder and commitment mutations into the final forced reread', async () => {
    const { result } = await ready();
    const first = Promise.withResolvers<BriefingResponse>();
    post.mockReturnValueOnce(first.promise).mockResolvedValueOnce(response(null));
    const invalidations: Promise<void>[] = [];
    act(() => {
      invalidations.push(result.current.invalidateSection('for_you'));
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    act(() => {
      invalidations.push(result.current.invalidateSection('reminders'));
    });
    await act(async () => {
      first.resolve(cards);
      await Promise.all(invalidations);
    });
    expect(post.mock.calls[1][1]).toEqual({ sections: ['for_you', 'reminders'] });
    expect(result.current.cards?.for_you.data?.open_loops).toEqual([]);
    expect(result.current.cards?.reminders.data?.items).toEqual([]);
  });

  it('retains paid generated text and its usage when only the cards are invalidated', async () => {
    const { result } = await ready();
    const build = Promise.withResolvers<BriefingResponse>();
    const paid = response();
    paid.synthesis = {
      text: 'New paid daily point',
      generated_at: '2026-10-15T09:00:00Z',
      usage: {
        tokens_in: 120,
        tokens_out: 30,
        tokens_cache: 10,
        cost_eur: 0.02,
        model_name: 'test-model',
      },
    };
    post.mockReturnValueOnce(build.promise).mockResolvedValueOnce(response(null));
    const requests: Promise<void>[] = [];
    act(() => {
      requests.push(result.current.refetchSection('all'));
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    act(() => {
      requests.push(result.current.invalidateSection('reminders'));
    });
    await act(async () => {
      build.resolve(paid);
      await Promise.all(requests);
    });
    expect(result.current.cards?.reminders.data?.items).toEqual([]);
    expect(result.current.text?.synthesis).toEqual(paid.synthesis);
    expect(post.mock.calls.filter(call => call[0] === '/briefing/refresh')).toHaveLength(1);
    expect(get).toHaveBeenCalledTimes(2);
  });
});

describe('briefing text from the first frame', () => {
  it('holds the text it will ask for as loading from the first render to its answer', async () => {
    // The initial text read is issued after the first commit; idle on those
    // frames, the welcome and the synthesis flashed absent and then shifted.
    const text = Promise.withResolvers<BriefingResponse>();
    get.mockImplementation((path: string) =>
      path.endsWith('/cards') ? Promise.resolve(cards) : text.promise
    );
    const frames: { loading: boolean; unavailable: boolean }[] = [];
    const { result } = renderHook(() => {
      const briefing = useBriefing();
      frames.push({ loading: briefing.textLoading, unavailable: briefing.textUnavailable });
      return briefing;
    });

    expect(frames[0]).toEqual({ loading: true, unavailable: false });
    await waitFor(() =>
      expect(get.mock.calls.filter(call => call[0].endsWith('/synthesis'))).toHaveLength(1)
    );
    await waitFor(() => expect(result.current.cards).toEqual(cards.cards));
    expect(frames.every(frame => frame.loading && !frame.unavailable)).toBe(true);

    await act(async () => text.resolve(cards));

    expect(result.current.textLoading).toBe(false);
    expect(result.current.text?.greeting.text).toBe('Good morning');
  });

  it('holds nothing as loading while the briefing is suspended', async () => {
    const { result } = renderHook(() => useBriefing(false));

    expect(result.current.textLoading).toBe(false);
    expect(result.current.loading).toBe(false);
    await act(async () => {});
    expect(get).not.toHaveBeenCalled();
  });

  it('holds nothing as loading without an account to read for', async () => {
    useAuth.mockReturnValue({ user: null });
    const { result } = renderHook(() => useBriefing());

    expect(result.current.textLoading).toBe(false);
    await act(async () => {});
    expect(result.current.textLoading).toBe(false);
    expect(get).not.toHaveBeenCalled();
  });
});

describe('briefing visibility and account lifetime', () => {
  it('waits for the initial card visibility and never waits for synthesis before draining an external mutation', async () => {
    const initial = Promise.withResolvers<BriefingResponse>();
    const text = Promise.withResolvers<BriefingResponse>();
    get.mockImplementation((path: string) =>
      path.endsWith('/cards') ? initial.promise : text.promise
    );
    post.mockResolvedValue(response(null));
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    expect(post).not.toHaveBeenCalled();
    await act(async () => initial.resolve(cards));
    await waitFor(() => expect(result.current.cards?.reminders.data?.items).toEqual([]));
    expect(result.current.textLoading).toBe(true);
    expect(post.mock.calls[0][1]).toEqual({ sections: ['reminders'] });
    await act(async () => text.resolve(cards));
  });

  it('retains a deferred mutation across an initial cards failure until explicit retry succeeds', async () => {
    get.mockImplementation((path: string) =>
      path.endsWith('/cards')
        ? Promise.reject(new Error('initial cards offline'))
        : Promise.resolve(cards)
    );
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.error?.message).toBe('initial cards offline'));
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    expect(post).not.toHaveBeenCalled();
    get.mockResolvedValue(cards);
    post.mockResolvedValue(response(null));
    await act(async () => result.current.refetchAll());
    await waitFor(() => expect(result.current.cards?.reminders.data?.items).toEqual([]));
    expect(post.mock.calls[0][1]).toEqual({ sections: ['reminders'] });
  });

  it('does not force hidden reminders or carry them into another card refresh', async () => {
    const hidden = response();
    hidden.cards.reminders.status = 'hidden';
    get.mockResolvedValue(hidden);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.cards?.reminders.status).toBe('hidden'));
    await act(async () => result.current.invalidateSection('reminders'));
    expect(post).not.toHaveBeenCalled();
    post.mockResolvedValue(hidden);
    await act(async () => result.current.invalidateSection('for_you'));
    expect(post.mock.calls[0][1]).toEqual({ sections: ['for_you'] });
  });

  it('drops a deferred initial invalidation when cards reveal the section is hidden', async () => {
    const initial = Promise.withResolvers<BriefingResponse>();
    get.mockImplementation((path: string) =>
      path.endsWith('/cards') ? initial.promise : Promise.resolve(cards)
    );
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    act(() => publishApplicationResources('one', new Set(['reminders'])));
    const hidden = response();
    hidden.cards.reminders.status = 'hidden';
    await act(async () => initial.resolve(hidden));
    expect(result.current.cards?.reminders.status).toBe('hidden');
    expect(post).not.toHaveBeenCalled();
    post.mockResolvedValue(hidden);
    await act(async () => result.current.invalidateSection('for_you'));
    expect(post.mock.calls[0][1]).toEqual({ sections: ['for_you'] });
  });

  it('rejects old replies and parked invalidation callbacks across accounts and unmount', async () => {
    const { result, rerender, unmount } = await ready();
    const old = Promise.withResolvers<BriefingResponse>();
    post.mockReturnValue(old.promise);
    const parked = result.current.invalidateSection;
    let invalidation: Promise<void> | undefined;
    act(() => {
      invalidation = parked('for_you');
    });
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockResolvedValue(response('two'));
    rerender();
    await waitFor(() => expect(result.current.cards?.reminders.data?.items[0]?.id).toBe('two'));
    await act(async () => {
      old.resolve(cards);
      await invalidation;
      await parked('for_you');
    });
    expect(result.current.cards?.reminders.data?.items[0]?.id).toBe('two');
    const retained = result.current.invalidateSection;
    unmount();
    await act(async () => retained('for_you'));
    expect(post).toHaveBeenCalledTimes(1);
  });
});
it('reports a failed explicit global generation even when a cards-only mutation finishes afterwards', async () => {
  const { result } = await ready();
  const build = Promise.withResolvers<BriefingResponse>();
  post.mockReturnValueOnce(build.promise).mockResolvedValueOnce(response(null));
  const requests: Promise<void>[] = [];
  act(() => {
    requests.push(result.current.refetchSection('all'));
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  act(() => {
    requests.push(result.current.invalidateSection('reminders'));
  });
  await act(async () => {
    build.reject(new Error('paid generation failed'));
    await Promise.all(requests);
  });
  expect(result.current.cards?.reminders.data?.items).toEqual([]);
  expect(result.current.error?.message).toBe('paid generation failed');
  expect(post.mock.calls.filter(call => call[0] === '/briefing/refresh')).toHaveLength(1);
});
it('uses a successful global recovery to learn initial visibility and drain a mutation received during that recovery', async () => {
  get.mockImplementation((path: string) =>
    path.endsWith('/cards')
      ? Promise.reject(new Error('initial cards offline'))
      : Promise.resolve(cards)
  );
  const { result } = renderHook(() => useBriefing());
  await waitFor(() => expect(result.current.error?.message).toBe('initial cards offline'));
  const global = Promise.withResolvers<BriefingResponse>();
  post.mockReturnValueOnce(global.promise).mockResolvedValueOnce(response(null));
  let refreshing: Promise<void> | undefined;
  act(() => {
    refreshing = result.current.refetchSection('all');
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  act(() => publishApplicationResources('one', new Set(['reminders'])));
  await act(async () => {
    global.resolve(response('before-cancel'));
    await refreshing;
  });
  await waitFor(() => expect(result.current.cards?.reminders.data?.items).toEqual([]));
  expect(result.current.error).toBeNull();
  expect(post.mock.calls.map(call => call[0])).toEqual([
    '/briefing/refresh',
    '/briefing/refresh-cards',
  ]);
  expect(post.mock.calls[1][1]).toEqual({ sections: ['reminders'] });
  expect(get).toHaveBeenCalledTimes(2);
});
