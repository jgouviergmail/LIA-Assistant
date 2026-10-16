import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import ConsumptionExportSection from '../ConsumptionExportSection';
const { useAuth, toast } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/hooks/useDebounce', () => ({ useDebounce: (value: unknown) => value }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => {
    resolve = done;
  });
  return { promise, resolve };
}
function csv() {
  return new Response('date,tokens\n2026-10-01,42', {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': 'attachment; filename="usage_2026-10.csv"',
    },
  });
}
function downloads() {
  return screen.getAllByRole('button', { name: /^settings\.user\.export\.download / });
}
function dates() {
  return {
    start: screen.getByLabelText('settings.user.export.start_date'),
    end: screen.getByLabelText('settings.user.export.end_date'),
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'one' } });
  vi.stubEnv('NEXT_PUBLIC_API_URL', '');
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:export');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});
describe('Consumption export downloads', () => {
  it.each(['token-usage', 'google-api-usage', 'stt-usage', 'tts-usage', 'consumption-summary'])(
    'downloads %s through the authenticated client with dates',
    async type => {
      const fetch = vi.fn().mockResolvedValue(csv());
      vi.stubGlobal('fetch', fetch);
      const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
      fireEvent.change(dates().start, { target: { value: '2026-10-01' } });
      fireEvent.change(dates().end, { target: { value: '2026-10-15' } });
      await user.click(
        downloads()[
          [
            'token-usage',
            'google-api-usage',
            'stt-usage',
            'tts-usage',
            'consumption-summary',
          ].indexOf(type)
        ]
      );
      await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
      expect(fetch).toHaveBeenCalledWith(
        `/api/v1/usage/export/${type}?start_date=2026-10-01&end_date=2026-10-15`,
        expect.objectContaining({ credentials: 'include', signal: expect.any(AbortSignal) })
      );
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:export');
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    }
  );
  it('shows an inline error and allows a deliberate retry', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } })
      )
      .mockResolvedValueOnce(csv());
    vi.stubGlobal('fetch', fetch);
    const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    await user.click(downloads()[0]);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('settings.user.export.error')
    );
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    await user.click(downloads()[0]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('blocks reversed dates before any request while retaining their values', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    fireEvent.change(dates().start, { target: { value: '2026-10-15' } });
    fireEvent.change(dates().end, { target: { value: '2026-10-01' } });
    expect(screen.getByRole('alert')).toHaveTextContent('settings.user.export.invalid_period');
    await user.click(downloads()[0]);
    expect(fetch).not.toHaveBeenCalled();
    expect(dates().start).toHaveValue('2026-10-15');
  });
  it('locks repeated synchronous export activations until the body completes', async () => {
    const pending = deferred<Response>();
    const fetch = vi.fn().mockReturnValue(pending.promise);
    vi.stubGlobal('fetch', fetch);
    renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    const button = downloads()[0];
    button.focus();
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveFocus();
    expect(button).toHaveAccessibleName(
      'settings.user.export.download settings.user.export.token_usage_title'
    );
    await act(async () => pending.resolve(csv()));
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    expect(button).toHaveFocus();
    expect(button).not.toBeDisabled();
  });
  it('aborts a departed account and suppresses its late download and toast', async () => {
    const pending = deferred<Response>();
    const fetch = vi.fn().mockReturnValue(pending.promise);
    vi.stubGlobal('fetch', fetch);
    const view = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    await view.user.click(downloads()[0]);
    useAuth.mockReturnValue({ user: { id: 'two' } });
    view.rerender(<ConsumptionExportSection lng="en" mode="user" />);
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    await act(async () => pending.resolve(csv()));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(downloads()[0]).not.toBeDisabled();
  });
  it('uses local civil-date presets including leap-February and all history', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2024, 2, 1, 0, 15));
    const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    await user.click(
      screen.getByRole('button', { name: 'settings.user.export.preset_last_month' })
    );
    expect(dates().start).toHaveValue('2024-02-01');
    expect(dates().end).toHaveValue('2024-02-29');
    await user.click(screen.getByRole('button', { name: 'settings.user.export.preset_all_time' }));
    expect(dates().start).toHaveValue('');
    expect(dates().end).toHaveValue('');
  });
  it.each([
    ['attachment; filename="journal.csv"', 'journal.csv'],
    ["attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.csv", 'résumé.csv'],
    ['attachment; filename*=UTF-8\'\'%XY; filename="fallback.csv"', 'fallback.csv'],
    [null, 'token-usage_export.csv'],
  ])('uses a safe server filename or the established fallback: %s', async (header, expected) => {
    const response = new Response('a,b\n1,2', { headers: { 'Content-Type': 'text/csv' } });
    if (header) response.headers.set('Content-Disposition', header);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    let savedName = '';
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      savedName = this.download;
    });
    const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    await user.click(downloads()[0]);
    await waitFor(() => expect(savedName).toBe(expected));
  });

  it('suppresses a CSV body that completes after the section has unmounted', async () => {
    const body = deferred<Blob>();
    const response = csv();
    vi.spyOn(response, 'blob').mockReturnValue(body.promise);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const view = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    await view.user.click(downloads()[0]);
    await waitFor(() => expect(response.blob).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => body.resolve(new Blob(['csv'])));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('releases the object URL and exposes failure when the browser cannot start saving', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(csv()));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('Download blocked');
    });
    const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
    await user.click(downloads()[0]);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('settings.user.export.error')
    );
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:export');
    expect(document.querySelector('a[download]')).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it.each([
    [new Date(2026, 2, 30, 0, 15), '2026-03-01', '2026-03-30'],
    [new Date(2026, 9, 26, 0, 15), '2026-09-27', '2026-10-26'],
  ] as const)(
    'exports exactly thirty inclusive civil dates across seasonal clock-change periods: %s',
    async (today, expectedStart, expectedEnd) => {
      vi.useFakeTimers({ toFake: ['Date'] });
      vi.setSystemTime(today);
      const { user } = renderWithProviders(<ConsumptionExportSection lng="en" mode="user" />);
      await user.click(
        screen.getByRole('button', { name: 'settings.user.export.preset_last_30_days' })
      );
      expect(dates().start).toHaveValue(expectedStart);
      expect(dates().end).toHaveValue(expectedEnd);
      const inclusiveCount = (Date.parse(expectedEnd) - Date.parse(expectedStart)) / 86_400_000 + 1;
      expect(inclusiveCount).toBe(30);
    }
  );

  it('sends a user filter only to the admin endpoint and clears it when mode changes', async () => {
    const fetch = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        url.includes('autocomplete')
          ? new Response(
              JSON.stringify({
                users: [
                  {
                    id: 'selected-user',
                    email: 'alice@example.com',
                    full_name: null,
                    is_active: true,
                  },
                ],
              }),
              { headers: { 'Content-Type': 'application/json' } }
            )
          : csv()
      )
    );
    vi.stubGlobal('fetch', fetch);
    const view = renderWithProviders(<ConsumptionExportSection lng="en" mode="admin" />);
    await view.user.type(screen.getByRole('combobox'), 'alice');
    await view.user.click(await screen.findByRole('option'));
    await view.user.click(
      screen.getAllByRole('button', { name: /^settings\.admin\.export\.download / })[0]
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/v1/admin/google-api/export/token-usage?user_id=selected-user',
      expect.objectContaining({ credentials: 'include' })
    );
    view.rerender(<ConsumptionExportSection lng="en" mode="user" />);
    await view.user.click(downloads()[0]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(2));
    expect(fetch).toHaveBeenLastCalledWith('/api/v1/usage/export/token-usage', expect.anything());
    expect(screen.getAllByRole('listitem')).toHaveLength(5);
  });
});
