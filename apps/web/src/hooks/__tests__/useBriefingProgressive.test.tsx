/**
 * The progressive dashboard (spec 2026-10-21 §5.8, D3): one act per page load,
 * its pending sections read one request each, its text once they all settled.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import type {
  BriefingInitialResponse,
  BriefingSection,
  BriefingTextResponse,
  CardSection,
  CardsBundle,
  SectionData,
} from '@/types/briefing';

const { get, post, text, useAuth, trackClientTiming } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  text: vi.fn(),
  useAuth: vi.fn(),
  trackClientTiming: vi.fn(),
}));
vi.mock('@/lib/product-telemetry', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/product-telemetry')>()),
  trackClientTiming,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  // The server answers a card's own route from the same state as the bundle routes: a
  // test hands it a snapshot (a bundle), and the section route serves the card it names.
  const sectionRoute = /^\/briefing\/sections\/([a-z_]+)\/refresh$/;
  const served = (path: string, value: unknown): unknown => {
    const card = sectionRoute.exec(path)?.[1];
    return card && value !== null && typeof value === 'object' && 'cards' in value
      ? (value as { cards: Record<string, unknown> }).cards[card]
      : value;
  };
  const dispatch = (path: string, ...rest: unknown[]) =>
    path === '/briefing/text'
      ? text(path, ...rest)
      : Promise.resolve(post(path, ...rest)).then(value => served(path, value));
  return { ...original, default: { get, post: dispatch } };
});
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
import { useBriefing } from '../useBriefing';
import { readAtMost } from '../useBriefingProgressive';

const INITIAL = '/briefing/cards/initial';
const AT = '2026-10-28T08:00:00Z';

function section<T extends SectionData>(status: CardSection['status'], data: T): CardSection<T> {
  return {
    status,
    data,
    generated_at: AT,
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const PENDING = section('pending', null);
const AGENDA = section('ok', {
  events: [{ title: 'Review', start_local: '10:00', end_local: null, location: null }],
});
const MAILS = section('ok', { items: [], total_unread_today: 2 });

function bundle(overrides: Partial<CardsBundle> = {}): CardsBundle {
  const quiet = section('empty', null);
  return {
    weather: quiet,
    agenda: quiet,
    mails: quiet,
    birthdays: quiet,
    reminders: section('ok', { items: [{ id: 'r', content: 'Call', trigger_at_local: '09:00' }] }),
    health: quiet,
    for_you: quiet,
    tasks: quiet,
    documents: quiet,
    workboard: quiet,
    ...overrides,
  } as CardsBundle;
}

function initial(pending: BriefingSection[], act = 'act-1'): BriefingInitialResponse {
  const cards = bundle(Object.fromEntries(pending.map(name => [name, PENDING])));
  return {
    cards,
    pending,
    act,
    act_expires_at: '2026-10-28T08:10:00Z',
    section_concurrency: 4,
    windows: {
      birthdays_horizon_days: 7,
      health_window_days: 14,
      agenda_lookahead_hours: 24,
      tasks_horizon_days: 7,
      weather_forecast_days: 5,
    },
  };
}

const READY: BriefingTextResponse = {
  greeting: { text: 'Good morning', generated_at: AT, usage: null },
  synthesis: { text: 'Your point', generated_at: AT, usage: null },
  reused: false,
  state: 'ready',
};

/** Section reads that wait until the test answers them, in the order they were asked. */
function heldSections() {
  const held = new Map<string, PromiseWithResolvers<CardSection>>();
  get.mockImplementation((path: string) => {
    if (path === INITIAL) return Promise.resolve(initial(['agenda', 'mails']));
    const answer = Promise.withResolvers<CardSection>();
    held.set(path, answer);
    return answer.promise;
  });
  return held;
}

const sectionReads = () => get.mock.calls.filter(call => call[0] !== INITIAL);

beforeEach(() => {
  vi.resetAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  text.mockResolvedValue(READY);
});

describe('the progressive dashboard', () => {
  it('renders local cards at once and reads each pending section of the act', async () => {
    const held = heldSections();
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));

    expect(result.current.cards?.reminders.status).toBe('ok');
    expect(result.current.cards?.agenda.status).toBe('pending');
    expect(sectionReads().map(call => [call[0], call[1].params])).toEqual([
      ['/briefing/sections/agenda', { act: 'act-1' }],
      ['/briefing/sections/mails', { act: 'act-1' }],
    ]);
    await act(async () => held.get('/briefing/sections/agenda')!.resolve(AGENDA));
    expect(result.current.cards?.agenda).toEqual(AGENDA);
    expect(result.current.cards?.mails.status).toBe('pending');
  });

  it('text read starts once every pending section settled', async () => {
    const held = heldSections();
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));

    await act(async () => held.get('/briefing/sections/agenda')!.resolve(AGENDA));
    expect(text).not.toHaveBeenCalled();
    expect(result.current.textLoading).toBe(true);
    await act(async () => held.get('/briefing/sections/mails')!.resolve(MAILS));

    await waitFor(() => expect(result.current.text?.greeting.text).toBe('Good morning'));
    expect(text).toHaveBeenCalledOnce();
    expect(text.mock.calls[0][1]).toEqual({ act: 'act-1', force: false });
  });

  it('a failed section read becomes an error card and the text still follows', async () => {
    const held = heldSections();
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));

    await act(async () => {
      held.get('/briefing/sections/agenda')!.reject(new Error('offline'));
      held.get('/briefing/sections/mails')!.resolve(MAILS);
    });

    await waitFor(() => expect(text).toHaveBeenCalledOnce());
    expect(result.current.cards?.agenda.status).toBe('error');
    expect(result.current.cards?.agenda.error_code).toBe('internal');
  });

  it('ignores a late section response after refresh', async () => {
    const held = heldSections();
    const fresh = section('ok', {
      events: [{ title: 'Refreshed', start_local: '11:00', end_local: null, location: null }],
    });
    post.mockResolvedValue(fresh);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));

    await act(async () => result.current.refetchSection('agenda'));
    expect(result.current.cards?.agenda).toEqual(fresh);
    await act(async () => held.get('/briefing/sections/agenda')!.resolve(AGENDA));

    expect(result.current.cards?.agenda).toEqual(fresh);
    expect(post.mock.calls.map(call => call[0])).toEqual(['/briefing/sections/agenda/refresh']);
  });

  it('ignores responses after logout and login', async () => {
    const held = heldSections();
    const { result, rerender } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));

    useAuth.mockReturnValue({ user: null });
    rerender();
    useAuth.mockReturnValue({ user: { id: 'two' } });
    get.mockImplementation((path: string) =>
      path === INITIAL
        ? Promise.resolve(initial(['agenda'], 'act-two'))
        : new Promise<CardSection>(() => {})
    );
    rerender();
    await waitFor(() => expect(result.current.cards?.agenda.status).toBe('pending'));
    await act(async () => {
      held.get('/briefing/sections/agenda')!.resolve(AGENDA);
      held.get('/briefing/sections/mails')!.resolve(MAILS);
    });

    expect(result.current.cards?.agenda.status).toBe('pending');
    expect(result.current.cards?.mails.status).toBe('empty');
    expect(text).not.toHaveBeenCalled();
  });

  it('refreshing one card sends one section request and no text request', async () => {
    get.mockResolvedValue(initial([]));
    post.mockResolvedValue(AGENDA);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(text).toHaveBeenCalledOnce());

    await act(async () => result.current.refetchSection('agenda'));

    expect(post.mock.calls.map(call => call[0])).toEqual(['/briefing/sections/agenda/refresh']);
    expect(text).toHaveBeenCalledOnce();
    expect(result.current.cards?.agenda).toEqual(AGENDA);
  });

  it('double press on refresh sends one request', async () => {
    get.mockResolvedValue(initial([]));
    const answer = Promise.withResolvers<CardSection>();
    post.mockReturnValue(answer.promise);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(text).toHaveBeenCalledOnce());

    const presses: Promise<void>[] = [];
    act(() => {
      presses.push(result.current.refetchSection('agenda'));
      presses.push(result.current.refetchSection('agenda'));
    });
    await act(async () => {
      answer.resolve(AGENDA);
      await Promise.all(presses);
    });

    expect(post).toHaveBeenCalledOnce();
  });

  it('sms signal drops text and hides sms items during a progressive load', async () => {
    const sms = section('ok', {
      timezone: 'Europe/Paris',
      total: 1,
      window_total: 1,
      window_start: AT,
      as_of: AT,
      latest_at: null,
      items: [
        {
          id: '10000000-0000-4000-8000-000000000001',
          sender: 'Alice',
          display_name: 'Alice',
          received_at: AT,
          date_kind: 'received',
          body_excerpt: 'PRIVATE',
          body_truncated: false,
        },
      ],
    });
    const first = initial(['agenda']);
    first.cards.sms = sms;
    const agenda = Promise.withResolvers<CardSection>();
    const answer = Promise.withResolvers<BriefingTextResponse>();
    get.mockImplementation((path: string) =>
      path === INITIAL ? Promise.resolve(first) : agenda.promise
    );
    text.mockReturnValue(answer.promise);
    post.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(result.current.cards?.sms?.data?.items).toHaveLength(1));
    await act(async () => agenda.resolve(AGENDA));
    await waitFor(() => expect(text).toHaveBeenCalledOnce());

    act(() => publishApplicationResources('one', new Set(['sms'])));
    expect(result.current.cards?.sms?.data?.items).toEqual([]);
    await act(async () => answer.resolve(READY));

    expect(result.current.text).toBeUndefined();
    expect(result.current.cards?.sms?.data?.items).toEqual([]);
    expect(post.mock.calls[0][0]).toBe('/briefing/sections/sms/refresh');
  });

  it('a changed context restarts the act once, and its text follows the new act', async () => {
    const changed = new ApiError('HTTP 409', 409, { detail: { code: 'briefing_context_changed' } });
    let acts = 0;
    get.mockImplementation((path: string) => {
      if (path === INITIAL) return Promise.resolve(initial(['agenda', 'mails'], `act-${++acts}`));
      return acts === 1 ? Promise.reject(changed) : Promise.resolve(AGENDA);
    });
    const { result } = renderHook(() => useBriefing());

    await waitFor(() => expect(text).toHaveBeenCalledOnce());
    expect(get.mock.calls.filter(call => call[0] === INITIAL)).toHaveLength(2);
    expect(text.mock.calls[0][1]).toEqual({ act: 'act-2', force: false });
    expect(result.current.cards?.agenda).toEqual(AGENDA);
  });

  it('a text refused for a changed context reads the new act text, nothing bought twice', async () => {
    const changed = new ApiError('HTTP 409', 409, { detail: { code: 'briefing_context_changed' } });
    let acts = 0;
    get.mockImplementation(() => Promise.resolve(initial([], `act-${++acts}`)));
    text.mockRejectedValueOnce(changed).mockResolvedValueOnce(READY);
    const { result } = renderHook(() => useBriefing());

    await waitFor(() => expect(result.current.text?.greeting.text).toBe('Good morning'));
    expect(text.mock.calls.map(call => call[1])).toEqual([
      { act: 'act-1', force: false },
      { act: 'act-2', force: false },
    ]);
  });

  it('after a text refused for a changed context, the new act holds its text skeleton until its sections settle', async () => {
    // Fresh review B5: the restart left the text « requested », so a retry button showed
    // while the new act's sections were pending, and pressing it bought a partial text.
    const changed = new ApiError('HTTP 409', 409, { detail: { code: 'briefing_context_changed' } });
    let acts = 0;
    const held = new Map<string, PromiseWithResolvers<CardSection>>();
    get.mockImplementation((path: string) => {
      if (path === INITIAL) {
        acts += 1;
        return Promise.resolve(initial(acts === 1 ? [] : ['agenda'], `act-${acts}`));
      }
      const answer = Promise.withResolvers<CardSection>();
      held.set(path, answer);
      return answer.promise;
    });
    text.mockRejectedValueOnce(changed).mockResolvedValueOnce(READY);
    const { result } = renderHook(() => useBriefing());

    await waitFor(() => expect(held.size).toBe(1));
    expect(result.current.textUnavailable).toBe(false);
    expect(result.current.textLoading).toBe(true);
    await act(async () => {
      [...held.values()][0].resolve(AGENDA);
    });

    await waitFor(() => expect(result.current.text?.greeting.text).toBe('Good morning'));
    expect(text.mock.calls.map(call => call[1])).toEqual([
      { act: 'act-1', force: false },
      { act: 'act-2', force: false },
    ]);
  });

  it('a refresh pressed while sections are pending reads no text before they settle', async () => {
    const held = heldSections();
    text.mockResolvedValue(READY);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(held.size).toBe(2));

    await act(async () => {
      void result.current.refetchAll();
    });

    expect(text).not.toHaveBeenCalled();
    await act(async () => {
      for (const answer of held.values()) answer.resolve(AGENDA);
    });
    await waitFor(() => expect(result.current.text?.greeting.text).toBe('Good morning'));
    expect(text).toHaveBeenCalledTimes(1);
  });

  it('a suspension aborts the section reads and the resumed page reads what is still pending', async () => {
    const held = heldSections();
    const { result, rerender } = renderHook(({ enabled }) => useBriefing(enabled), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(sectionReads()).toHaveLength(2));
    const signal: AbortSignal = sectionReads()[0][1].signal;

    rerender({ enabled: false });
    expect(signal.aborted).toBe(true);
    await act(async () => held.get('/briefing/sections/agenda')!.resolve(AGENDA));
    rerender({ enabled: true });

    await waitFor(() => expect(sectionReads().length).toBeGreaterThanOrEqual(4));
    expect(result.current.cards?.agenda.status).toBe('pending');
  });

  it('a push while a section is still pending never reads that section twice', async () => {
    // The bundle route would have re-read the pending agenda live beside its own request.
    const held = heldSections();
    const reminders = section('ok', { items: [] });
    post.mockResolvedValue(reminders);
    const { result } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));

    act(() => publishApplicationResources('one', new Set(['reminders'])));
    await waitFor(() => expect(post).toHaveBeenCalledOnce());

    expect(post.mock.calls.map(call => call[0])).toEqual(['/briefing/sections/reminders/refresh']);
    await act(async () => {
      for (const answer of held.values()) answer.resolve(AGENDA);
    });
    expect(sectionReads()).toHaveLength(2); // each pending section read once, on its own route
    expect(result.current.cards?.reminders.data).toEqual({ items: [] });
  });

  it('a text written about withdrawn SMS is not shown and the SMS card is reread', async () => {
    get.mockResolvedValue(initial([]));
    text.mockResolvedValue({ ...READY, state: 'sms_stale' });
    post.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useBriefing());

    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    expect(post.mock.calls[0][0]).toBe('/briefing/sections/sms/refresh');
    expect(result.current.text).toBeUndefined();
    expect(result.current.textUnavailable).toBe(true);
  });

  it('a context that keeps changing stops after bounded new acts and leaves a retry', async () => {
    const changed = new ApiError('HTTP 409', 409, { detail: { code: 'briefing_context_changed' } });
    let acts = 0;
    get.mockImplementation((path: string) =>
      path === INITIAL
        ? Promise.resolve(initial(['agenda'], `act-${++acts}`))
        : Promise.reject(changed)
    );
    const { result } = renderHook(() => useBriefing());

    await waitFor(() => expect(result.current.cards?.agenda.status).toBe('error'));
    expect(acts).toBe(3);
    await act(async () => {});
    expect(acts).toBe(3);
  });
});

describe('dashboard timings', () => {
  it('emits dashboard timings once per load', async () => {
    const held = heldSections();
    const { result, rerender } = renderHook(() => useBriefing());
    await waitFor(() => expect(sectionReads()).toHaveLength(2));
    const names = () => trackClientTiming.mock.calls.map(call => call[0]);

    expect(names()).toEqual(['dashboard_first_card']);
    await act(async () => held.get('/briefing/sections/agenda')!.resolve(AGENDA));
    expect(names()).toEqual(['dashboard_first_card']);
    await act(async () => held.get('/briefing/sections/mails')!.resolve(MAILS));
    await waitFor(() => expect(result.current.text).toBeDefined());
    rerender();

    expect(names()).toEqual(['dashboard_first_card', 'dashboard_all_cards', 'dashboard_text']);
    for (const call of trackClientTiming.mock.calls) expect(call[1]).toBeGreaterThanOrEqual(0);
  });
});

describe('readAtMost', () => {
  it('never runs more than its limit at once and runs every item', async () => {
    let running = 0;
    let peak = 0;
    const done: number[] = [];
    await readAtMost([1, 2, 3, 4, 5, 6, 7], 3, async item => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise(resolve => setTimeout(resolve, 1));
      running -= 1;
      done.push(item);
    });
    expect(peak).toBe(3);
    expect(done.sort()).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });
});
