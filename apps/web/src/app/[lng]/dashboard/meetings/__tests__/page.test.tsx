/**
 * The meetings list page: skeleton on first load, an actionable empty state,
 * one named row per meeting, pagination only past one page.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { MeetingSummary } from '@/types/meetings';
import type { AppConfig, useAppConfig as useAppConfigFn } from '@/hooks/useAppConfig';
import { appConfigFixture } from '@/__tests__/fixtures/app-config';

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'meeting-list-owner' } }) }));

const appConfig = vi.hoisted((): { value: AppConfig | null } => ({ value: null }));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: (): ReturnType<typeof useAppConfigFn> => ({
    config: appConfig.value,
    loading: false,
    error: null,
  }),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const list = vi.hoisted(() => ({
  meetings: [] as MeetingSummary[],
  total: 0,
  isLoading: false,
  isUnavailable: false,
  isDeleting: false,
  bulkDelete: vi.fn(),
  refetch: vi.fn(),
  read: vi.fn(),
}));
vi.mock('@/hooks/useMeetings', () => ({
  useMeetingList: (...args: unknown[]) => {
    list.read(...args);
    return { ...list, error: null };
  },
}));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'en' }));
const recorder = vi.hoisted(() => ({
  value: null as { start: () => Promise<void>; isLive: boolean; phase: string } | null,
}));
vi.mock('@/components/meetings/MeetingRecorderProvider', () => ({
  useMeetingRecorderContext: () => recorder.value,
}));
const push = vi.fn();
// The origin travels in the URL, so the page's search params are part of
// its input — the global setup mock answers an empty set.
const searchParams = vi.hoisted(() => ({ value: new URLSearchParams() }));
vi.mock('next/navigation', async importOriginal => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useSearchParams: () => searchParams.value,
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

import MeetingsPage from '../page';
import { MeetingsWorkspace } from '@/components/meetings/MeetingsWorkspace';

function summary(over: Partial<MeetingSummary> = {}): MeetingSummary {
  return {
    id: 'm1',
    status: 'ready',
    stage: null,
    title: 'Point projet',
    started_at: '2026-09-02T10:00:00Z',
    stopped_at: '2026-09-02T11:00:00Z',
    audio_duration_seconds: 3600,
    participants_count: 3,
    action_items_count: 2,
    index_state: 'indexed',
    stt_provider: 'elevenlabs',
    total_cost_eur: null,
    last_error_code: null,
    template_ref: null,
    template_name: null,
    template_selection: null,
    source_meeting_id: null,
    ...over,
  };
}

const params = Promise.resolve({ lng: 'en' });

beforeEach(() => {
  vi.clearAllMocks();
  appConfig.value = null;
  searchParams.value = new URLSearchParams();
  window.history.replaceState({}, '', '/');
  list.meetings = [];
  list.total = 0;
  list.isLoading = false;
  list.isUnavailable = false;
  list.isDeleting = false;
  list.bulkDelete.mockResolvedValue({ deleted: [], skipped: [] });
});

describe('MeetingsPage', () => {
  it('debounces typing, resets the page, retains focus and restores browser history', async () => {
    searchParams.value = new URLSearchParams('page=3&from=chat');
    list.meetings = [summary()];
    list.total = 60;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    const input = screen.getByRole('searchbox');
    await user.type(input, 'budget');
    expect(list.read).toHaveBeenLastCalledWith(20, 40, true, '');
    await waitFor(() => expect(list.read).toHaveBeenLastCalledWith(20, 0, true, 'budget'));
    expect(input).toHaveFocus();
    // The address follows in an effect after the render that read: wait for it,
    // or a loaded run checks it before the effect ran.
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get('q')).toBe('budget')
    );
    expect(new URLSearchParams(window.location.search).has('page')).toBe(false);
    act(() => {
      window.history.pushState({}, '', '?page=2&q=autre');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() => expect(input).toHaveValue('autre'));
    expect(list.read).toHaveBeenLastCalledWith(20, 20, true, 'autre');
    await user.click(screen.getByRole('button', { name: 'settings.search.clear' }));
    expect(list.read).toHaveBeenLastCalledWith(20, 0, true, '');
    expect(screen.getByRole('searchbox')).toBe(input);
  });

  it('searches on the server and preserves query and origin on the detail link', async () => {
    searchParams.value = new URLSearchParams('q=Caf%C3%A9&page=3&from=chat');
    list.meetings = [summary()];
    list.total = 60;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByRole('searchbox')).toHaveValue('Café');
    expect(list.read).toHaveBeenLastCalledWith(20, 40, true, 'Café');
    expect(screen.getByRole('link', { name: 'Point projet' })).toHaveAttribute(
      'href',
      '/en/dashboard/meetings/m1?page=3&q=Caf%C3%A9&from=chat'
    );
    searchParams.value = new URLSearchParams();
  });

  it('distinguishes a filtered empty result and keeps its search control mounted', () => {
    searchParams.value = new URLSearchParams('q=absent');
    const { rerender } = renderWithProviders(<MeetingsPage params={params} />);
    const input = screen.getByRole('searchbox');
    expect(screen.getByText('meetings.list.no_results_title')).toBeInTheDocument();
    list.isLoading = true;
    rerender(<MeetingsPage params={params} />);
    expect(screen.getByRole('searchbox')).toBe(input);
    searchParams.value = new URLSearchParams();
  });

  it('announces the first load', () => {
    list.isLoading = true;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('offers the chat when there is no meeting yet', async () => {
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText('meetings.list.empty_title')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'meetings.list.empty_action' }));
    expect(push).toHaveBeenCalledWith('/dashboard/chat');
  });

  it('carries a validated list page and origin through a detail link', () => {
    searchParams.value = new URLSearchParams('page=3&from=relations');
    list.meetings = [summary()];
    list.total = 60;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByRole('link', { name: 'Point projet' })).toHaveAttribute(
      'href',
      '/en/dashboard/meetings/m1?page=3&from=relations'
    );
    searchParams.value = new URLSearchParams();
  });

  it('names every row after its meeting and opens it', async () => {
    list.meetings = [
      summary(),
      summary({ id: 'm2', title: null, status: 'processing', stage: 'transcribing' }),
    ];
    list.total = 2;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.queryByText('meetings.list.total')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Point projet' })).toHaveAttribute(
      'href',
      '/en/dashboard/meetings/m1'
    );
    expect(screen.getByText('meetings.list.untitled')).toBeInTheDocument();
    expect(screen.getAllByText('meetings.stage.transcribing')).toHaveLength(2);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('paginates only when the total exceeds one page', () => {
    list.meetings = [summary()];
    list.total = 45;
    renderWithProviders(<MeetingsPage params={params} />);
    const nav = screen.getByRole('navigation', { name: 'common.pagination.label' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^common.previous/ })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    expect(screen.getByRole('button', { name: /^common.next/ })).not.toHaveAttribute(
      'aria-disabled',
      'true'
    );
  });
});

describe('MeetingsPage — cost in the row', () => {
  it('appends what a meeting cost when anything priced was spent, nothing otherwise', () => {
    list.meetings = [summary({ total_cost_eur: 0.0167 }), summary({ id: 'm2', title: 'Free' })];
    list.total = 2;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText(/€0\.0167/)).toBeInTheDocument();
    expect(screen.getAllByText(/€/)).toHaveLength(1);
  });
});

describe('MeetingsPage — individual deletion', () => {
  it('offers a named delete action per row and refuses an in-flight row', async () => {
    list.meetings = [
      summary(),
      summary({ id: 'm2', title: 'Daily', status: 'processing', stage: 'transcribing' }),
    ];
    list.total = 2;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    const blocked = screen.getByRole('button', { name: 'common.delete · Daily' });
    expect(blocked).toHaveAttribute('aria-disabled', 'true');
    await user.click(blocked);
    expect(list.bulkDelete).not.toHaveBeenCalled();
  });

  it('deletes only the clicked row without a confirmation dialog', async () => {
    list.meetings = [summary(), summary({ id: 'm2', title: 'Daily' })];
    list.total = 2;
    list.bulkDelete.mockResolvedValue({ deleted: ['m1'], skipped: [] });
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'common.delete · Point projet' }));
    await waitFor(() => expect(list.bulkDelete).toHaveBeenCalledExactlyOnceWith(['m1']));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith('meetings.list.bulk_deleted');
    expect(list.refetch).toHaveBeenCalledOnce();
  });

  it('steps back when deletion empties the last page', async () => {
    list.meetings = [summary()];
    list.total = 21;
    list.bulkDelete.mockResolvedValue({ deleted: ['m1'], skipped: [] });
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getByRole('button', { name: /^common.next/ }));
    await user.click(screen.getByRole('button', { name: 'common.delete · Point projet' }));
    await waitFor(() => expect(list.bulkDelete).toHaveBeenCalledWith(['m1']));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^common.previous/ })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    );
  });
});

describe('MeetingsPage — toolbar and format (ADR-259)', () => {
  it('records from the toolbar without a templates shortcut', async () => {
    const start = vi.fn().mockResolvedValue(undefined);
    recorder.value = { start, isLive: false, phase: 'idle' };
    list.meetings = [summary()];
    list.total = 1;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    await user.click(screen.getByRole('button', { name: 'meetings.list.record' }));
    expect(start).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole('button', { name: 'meetings.list.templates' })
    ).not.toBeInTheDocument();
    recorder.value = null;
  });

  it('hides the record CTA without a recorder and states it while live', () => {
    recorder.value = null;
    list.meetings = [summary()];
    list.total = 1;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.queryByRole('button', { name: 'meetings.list.record' })).not.toBeInTheDocument();

    recorder.value = { start: vi.fn(), isLive: true, phase: 'recording' };
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByRole('button', { name: 'meetings.list.record' })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    recorder.value = null;
  });

  it('names the format of a meeting in its row', () => {
    list.meetings = [summary({ template_name: 'Daily standup' })];
    list.total = 1;
    renderWithProviders(<MeetingsPage params={params} />);
    expect(screen.getByText(/Daily standup/)).toBeInTheDocument();
  });
});

describe('MeetingsPage — navigation', () => {
  it.each(['', 'relations', 'https://evil.example.com'])(
    'has no previous-page action for origin %s',
    origin => {
      searchParams.value = new URLSearchParams({ from: origin });
      renderWithProviders(<MeetingsPage params={params} />);
      expect(
        screen.queryByRole('button', { name: /navigation\.(chat|relations)/ })
      ).not.toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    }
  );
});

describe('MeetingsPage — chronology content and independent controls', () => {
  it('keeps the full title link, real end time and zero audio duration available', async () => {
    const title = 'A very long meeting title which remains readable and opens its real report';
    list.meetings = [summary({ title, audio_duration_seconds: 0, stt_provider: 'fishaudio' })];
    list.total = 1;
    const { user } = renderWithProviders(<MeetingsPage params={params} />);
    const link = screen.getByRole('link', { name: title });
    expect(link).toHaveAttribute('href', '/en/dashboard/meetings/m1');
    expect(document.querySelector('time[datetime="2026-09-02T11:00:00Z"]')).toBeInTheDocument();
    expect(screen.getByText('0:00')).toBeInTheDocument();
    expect(screen.getByText('meetings.banner.engine.fishaudio')).toBeInTheDocument();
    const details = document.querySelector('details');
    expect(details).not.toHaveAttribute('open');
    await user.click(screen.getByText('common.details'));
    expect(details).toHaveAttribute('open');
    expect(push).not.toHaveBeenCalled();
    expect(link).toBeInTheDocument();
  });
});

describe('MeetingsPage — eligibility changes', () => {
  it('rechecks row eligibility after an invalidation', async () => {
    list.meetings = [summary()];
    list.total = 1;
    const view = renderWithProviders(<MeetingsPage params={params} />);
    const button = screen.getByRole('button', { name: 'common.delete · Point projet' });
    list.meetings = [summary({ status: 'processing', stage: 'transcribing' })];
    view.rerender(<MeetingsPage params={params} />);
    expect(button).toHaveAttribute('aria-disabled', 'true');
    await view.user.click(button);
    expect(list.bulkDelete).not.toHaveBeenCalled();
    list.meetings = [summary()];
    view.rerender(<MeetingsPage params={params} />);
    expect(button).toHaveAttribute('aria-disabled', 'false');
  });
});

it('keeps embedded meeting search, paging and detail selection inside its host', async () => {
  searchParams.value = new URLSearchParams('q=unrelated&page=3');
  window.history.replaceState({}, '', '/en/world-preview?shared=1&resume=1');
  const original = window.location.href;
  list.meetings = [summary()];
  list.total = 60;
  const open = vi.fn();
  const { user } = renderWithProviders(
    <MeetingsWorkspace lng="en" embedded onOpenMeeting={open} />
  );
  expect(screen.getByRole('searchbox')).toHaveValue('');
  expect(list.read).toHaveBeenLastCalledWith(20, 0, true, '');
  await user.type(screen.getByRole('searchbox'), 'budget');
  await waitFor(() => expect(list.read).toHaveBeenLastCalledWith(20, 0, true, 'budget'));
  expect(window.location.href).toBe(original);
  await user.click(screen.getByRole('button', { name: 'Point projet' }));
  expect(open).toHaveBeenCalledExactlyOnceWith('m1');
  expect(push).not.toHaveBeenCalled();
  expect(screen.queryByRole('link', { name: 'Point projet' })).not.toBeInTheDocument();
});

describe('meeting import across native and world workspaces', () => {
  it.each([false, true])('offers file import without a recorder (embedded: %s)', embedded => {
    recorder.value = null;
    appConfig.value = appConfigFixture({
      features: { meetings_enabled: true, meetings_import_enabled: true },
    });
    renderWithProviders(
      embedded ? <MeetingsWorkspace lng="en" embedded /> : <MeetingsPage params={params} />
    );
    expect(screen.getByRole('button', { name: 'meetings.list.import' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'meetings.list.record' })).not.toBeInTheDocument();
  });
});
