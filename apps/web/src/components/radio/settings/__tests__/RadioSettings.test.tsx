/**
 * The radio's settings: every choice offered is the API's own, every change is
 * saved, a list the API requires non-empty keeps its last item, the language
 * maximum holds, and a site is checked before it is added — the real radio
 * hooks, against a fake API.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  answerConfirmDialog,
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import {
  radioBaseSource,
  radioOptions,
  radioOwnSource,
  radioPreferences,
  radioSources,
} from '@/lib/radio/__tests__/fixtures';
import type {
  RadioBudget,
  RadioCustomSource,
  RadioDiscovery,
  RadioOptions,
  RadioPreferences,
  RadioSources,
} from '@/lib/radio/types';
import { RadioSettings } from '../RadioSettings';

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/usePersonality', () => ({
  usePersonality: () => ({
    personalities: [],
    currentPersonality: null,
    currentPersonalityId: null,
    loading: false,
    refreshing: false,
    updating: false,
    error: null,
    updatePersonality: vi.fn(),
    refetch: vi.fn(),
  }),
}));

afterEach(() => vi.clearAllMocks());

/** The radio's day, well under its bound. */
const BUDGET: RadioBudget = { limit_eur: 2, spent_eur: 0.1, window_hours: 24, lifts_at: null };

/** The newsroom the fake API holds: every write to it is seen by the next read. */
interface Newsroom {
  view: RadioSources;
  reads: number;
}

async function openSection(user: { click: (element: Element) => Promise<void> }, title: string) {
  await user.click(await screen.findByText(`radio.settings.${title}.title`));
}

function serve(
  options: RadioOptions,
  preferences: RadioPreferences,
  own: RadioCustomSource[] = []
): Newsroom {
  const newsroom: Newsroom = { view: radioSources({ own }), reads: 0 };
  mockApi.get.mockImplementation(async (endpoint: string) => {
    if (endpoint === RADIO_ENDPOINTS.options) return options;
    if (endpoint === RADIO_ENDPOINTS.preferences) return preferences;
    if (endpoint === RADIO_ENDPOINTS.budget) return BUDGET;
    if (endpoint === RADIO_ENDPOINTS.sources) {
      newsroom.reads += 1;
      return newsroom.view;
    }
    throw new Error(`unexpected read ${endpoint}`);
  });
  mockApi.put.mockImplementation(async (_endpoint: string, body: RadioPreferences) => body);
  mockApi.delete.mockImplementation(async (endpoint: string) => {
    const gone = newsroom.view.own.find(site => endpoint === RADIO_ENDPOINTS.source(site.id));
    if (gone) {
      newsroom.view = { ...newsroom.view, own: newsroom.view.own.filter(s => s !== gone) };
    }
    return undefined;
  });
  mockApi.patch.mockImplementation(async (endpoint: string, body: Partial<RadioCustomSource>) => {
    newsroom.view = {
      ...newsroom.view,
      own: newsroom.view.own.map(site =>
        endpoint === RADIO_ENDPOINTS.source(site.id) ? { ...site, ...body } : site
      ),
    };
    return undefined;
  });
  return newsroom;
}

describe('RadioSettings', () => {
  it('starts with descriptive settings sections closed and spending visible', async () => {
    serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    for (const section of ['programmes', 'sources', 'news', 'voices', 'listening']) {
      const title = await screen.findByText(`radio.settings.${section}.title`);
      const summary = title.closest('summary');
      expect(summary).toHaveTextContent(
        `radio.settings.${section}.${section === 'programmes' ? 'summary' : 'description'}`
      );
      expect(summary?.parentElement).not.toHaveAttribute('open');
    }
    expect(screen.queryByRole('switch', { name: 'radio.settings.source.health' })).toBeNull();
    expect(await screen.findByText(/^radio\.settings\.budget\.spent/)).toBeInTheDocument();
    expect(screen.getByText('radio.settings.budget.title').closest('details')).toHaveAttribute(
      'open'
    );
    await openSection(user, 'sources');
    expect(
      await screen.findByRole('switch', { name: 'radio.settings.source.health' })
    ).toBeVisible();
  });

  it('offers what the API publishes and saves a silenced source', async () => {
    serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'sources');

    const health = await screen.findByRole('switch', { name: 'radio.settings.source.health' });
    expect(screen.getAllByRole('switch', { name: /radio\.settings\.source\./ })).toHaveLength(4);
    expect(
      screen.getByRole('switch', { name: 'radio.settings.source.sent_mails' })
    ).toBeChecked();
    expect(health).toBeChecked();

    await user.click(health);

    await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
    const [endpoint, body] = mockApi.put.mock.calls[0];
    expect(endpoint).toBe(RADIO_ENDPOINTS.preferences);
    expect(body.disabled_sources).toEqual(['health']);
    expect(health).not.toBeChecked();
  });

  it('names the station as the listener types it, saved when they leave the field', async () => {
    serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'voices');

    const name = await screen.findByRole('textbox', { name: 'radio.settings.voices.station_name' });
    expect(name).toHaveAttribute('maxLength', '40'); // the bound the API publishes
    expect(name).toHaveAccessibleDescription(/radio\.settings\.voices\.station_name_hint/);
    await user.type(name, '  Radio   Alex ');
    expect(mockApi.put).not.toHaveBeenCalled(); // no save per keystroke
    await user.tab();

    await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
    expect(mockApi.put.mock.calls[0][1].station_name).toBe('Radio Alex');
    expect(name).toHaveValue('Radio Alex');
  });

  it('saves the name on Enter and gives the language’s name back when emptied', async () => {
    serve(radioOptions(), radioPreferences({ station_name: 'Radio Alex' }));
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'voices');

    const name = await screen.findByRole('textbox', { name: 'radio.settings.voices.station_name' });
    expect(name).toHaveValue('Radio Alex');
    await user.clear(name);
    await user.keyboard('{Enter}');

    await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
    expect(mockApi.put.mock.calls[0][1].station_name).toBeNull();
    expect(name).toHaveFocus(); // Enter saves in place: the field keeps the focus
  });

  it('saves nothing on the Enter that picks an input method’s candidate', async () => {
    serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="zh" />);

    await openSection(user, 'voices');

    const name = await screen.findByRole('textbox', { name: 'radio.settings.voices.station_name' });
    fireEvent.change(name, { target: { value: 'xiao' } });
    fireEvent.keyDown(name, { key: 'Enter', isComposing: true });
    expect(mockApi.put).not.toHaveBeenCalled();
    expect(name).toHaveValue('xiao');
  });

  it('shows the name as it would be saved, saving nothing when it did not change', async () => {
    serve(radioOptions(), radioPreferences({ station_name: 'Radio Alex' }));
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'voices');

    const name = await screen.findByRole('textbox', { name: 'radio.settings.voices.station_name' });
    await user.type(name, '   ');
    await user.tab();

    expect(name).toHaveValue('Radio Alex');
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('gives the saved name back when the API refuses the new one', async () => {
    serve(radioOptions(), radioPreferences({ station_name: 'Radio Alex' }));
    mockApi.put.mockRejectedValue(new ApiError('refused', 422, { detail: 'invalid' }));
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'voices');

    const name = await screen.findByRole('textbox', { name: 'radio.settings.voices.station_name' });
    await user.clear(name);
    await user.type(name, 'Radio Bob');
    await user.tab();

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(name).toHaveValue('Radio Alex'));
  });

  it('saves the verification chosen, each mode named', async () => {
    serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'listening');

    const all = await screen.findByRole('radio', { name: 'radio.settings.verification.all' });
    expect(all).toHaveAccessibleDescription('radio.settings.listening.verification_hint');
    expect(screen.getByRole('radio', { name: 'radio.settings.verification.news' })).toBeChecked();
    await user.click(all);

    await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
    expect(mockApi.put.mock.calls[0][1].verification).toBe('all');
    expect(all).toBeChecked();
  });

  it('shows the instance default as the choice of a listener who never chose', async () => {
    serve(radioOptions({ verification_default: 'off' }), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'listening');

    const off = await screen.findByRole('radio', { name: 'radio.settings.verification.off' });
    expect(off).toBeChecked();
    expect(
      screen.getByRole('radio', { name: 'radio.settings.verification.news' })
    ).not.toBeChecked();
  });

  it('unticks a base source, saves it, and reads the newsroom again', async () => {
    const newsroom = serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const [wire] = await screen.findAllByRole('checkbox', {
      name: 'radio.settings.news.with_language',
    });
    expect(wire).toBeChecked(); // every base source is heard by default
    const readsBefore = newsroom.reads;
    await user.click(wire);

    await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
    expect(mockApi.put.mock.calls[0][1].disabled_feeds).toEqual([radioBaseSource().url]);
    await waitFor(() => expect(newsroom.reads).toBe(readsBefore + 1)); // the totals move
    expect(wire).not.toBeChecked();
  });

  it('says what the newsroom holds, and which source fails', async () => {
    serve(radioOptions(), radioPreferences());
    const failing = radioSources({ base: [radioBaseSource({ failing: true })] });
    mockApi.get.mockImplementation(async (endpoint: string) => {
      if (endpoint === RADIO_ENDPOINTS.sources) return failing;
      if (endpoint === RADIO_ENDPOINTS.options) return radioOptions();
      if (endpoint === RADIO_ENDPOINTS.preferences) return radioPreferences();
      return BUDGET;
    });
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    expect(await screen.findByText('radio.settings.news.totals')).toBeInTheDocument();
    const [wire] = screen.getAllByRole('checkbox', { name: 'radio.settings.news.with_language' });
    expect(wire).toHaveAccessibleDescription(/radio\.settings\.news\.failing/);
  });

  it('shows a small site mark without sending the page as a referrer, then falls back', async () => {
    serve(radioOptions(), radioPreferences());
    const { user, container } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const mark = await waitFor(() => {
      const image = container.querySelector<HTMLImageElement>('img[src="https://feeds.example/favicon.ico"]');
      expect(image).not.toBeNull();
      return image!;
    });
    expect(mark).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(mark).toHaveAttribute('alt', '');
    fireEvent.error(mark);
    expect(container.querySelector('img[src="https://feeds.example/favicon.ico"]')).toBeNull();
    expect(
      screen.getAllByRole('checkbox', { name: 'radio.settings.news.with_language' })[0]
    ).toBeVisible();
  });

  it('forgets what the listener heard only once they confirm it', async () => {
    const newsroom = serve(radioOptions(), radioPreferences());
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const forget = await screen.findByRole('button', { name: 'radio.settings.news.forget' });
    await user.click(forget);
    await answerConfirmDialog(user, false);
    expect(mockApi.delete).not.toHaveBeenCalled();

    const readsBefore = newsroom.reads;
    await user.click(forget);
    await answerConfirmDialog(user, true);
    await waitFor(() => expect(mockApi.delete).toHaveBeenCalledTimes(1));
    expect(mockApi.delete.mock.calls[0][0]).toBe(RADIO_ENDPOINTS.heard);
    await waitFor(() => expect(newsroom.reads).toBe(readsBefore + 1));
    expect(toast.success).toHaveBeenCalledWith('radio.settings.news.forgotten');
  });

  it('removes a site the listener added', async () => {
    serve(radioOptions(), radioPreferences(), [
      radioOwnSource({ id: 's9', title: 'A blog', language: null }),
    ]);
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    expect(await screen.findByText('A blog')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'radio.settings.sites.remove' }));

    await waitFor(() => expect(screen.queryByText('A blog')).toBeNull());
    expect(mockApi.delete.mock.calls[0][0]).toBe(RADIO_ENDPOINTS.source('s9'));
  });

  it('pauses a site and gives it back, and renames it the way the API folds a name', async () => {
    serve(radioOptions(), radioPreferences(), [
      radioOwnSource({ id: 's3', title: 'A blog', language: null }),
    ]);
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const running = await screen.findByRole('checkbox', { name: 'A blog' });
    expect(running).toBeChecked();
    await user.click(running);
    await waitFor(() =>
      expect(mockApi.patch).toHaveBeenCalledWith(
        RADIO_ENDPOINTS.source('s3'),
        { paused: true },
        undefined
      )
    );
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'A blog' })).not.toBeChecked());
    expect(screen.getByText('radio.settings.sites.paused')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'A blog' }));
    await waitFor(() =>
      expect(mockApi.patch).toHaveBeenLastCalledWith(
        RADIO_ENDPOINTS.source('s3'),
        { paused: false },
        undefined
      )
    );
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'A blog' })).toBeChecked());

    const rename = screen.getByRole('button', { name: 'radio.settings.sites.rename' });
    await user.click(rename);
    const dialog = await screen.findByRole('dialog');
    const field = within(dialog).getByRole('textbox', {
      name: 'radio.settings.sites.rename_label',
    });
    await user.clear(field);
    await user.type(field, '  My   <blog> ');
    await user.click(
      within(dialog).getByRole('button', { name: 'radio.settings.sites.rename_save' })
    );
    await waitFor(() =>
      expect(mockApi.patch).toHaveBeenLastCalledWith(
        RADIO_ENDPOINTS.source('s3'),
        { title: 'My blog' },
        undefined
      )
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // The dialog has no trigger of its own: the row's button gets the focus back.
    await waitFor(() => expect(rename).toHaveFocus());
  });

  it('renames nothing when the listener leaves the dialog, and gives the focus back', async () => {
    serve(radioOptions(), radioPreferences(), [
      radioOwnSource({ id: 's4', title: 'A blog', language: null }),
    ]);
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const rename = await screen.findByRole('button', { name: 'radio.settings.sites.rename' });
    await user.click(rename);
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox'), ' again');
    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(rename).toHaveFocus());
    expect(mockApi.patch).not.toHaveBeenCalled();
  });

  it('checks a site before adding it, and says why one cannot be added', async () => {
    const newsroom = serve(radioOptions(), radioPreferences());
    const refused: RadioDiscovery = {
      outcome: 'not_public',
      feed_url: null,
      title: null,
      language: null,
      entries: null,
    };
    const found: RadioDiscovery = {
      outcome: 'found',
      feed_url: 'https://site.example.org/feed/',
      title: 'Site news',
      language: 'en',
      entries: 12,
    };
    const created = radioOwnSource({
      id: 's1',
      feed_url: 'https://site.example.org/feed/',
      title: 'Site news',
      language: 'en',
    });
    mockApi.post.mockImplementation(async (endpoint: string) => {
      if (endpoint === RADIO_ENDPOINTS.sourcePreview) {
        return mockApi.post.mock.calls.length === 1 ? refused : found;
      }
      newsroom.view = { ...newsroom.view, own: [...newsroom.view.own, created] };
      return created;
    });
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const address = await screen.findByRole('textbox', { name: 'radio.settings.sites.address' });
    await user.type(address, 'intranet.example');
    await user.click(screen.getByRole('button', { name: 'radio.settings.sites.check' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'radio.settings.sites.outcome.not_public'
    );
    expect(screen.queryByRole('button', { name: 'radio.settings.sites.add' })).toBeNull();

    await user.clear(address);
    await user.type(address, 'site.example.org');
    await user.click(screen.getByRole('button', { name: 'radio.settings.sites.check' }));
    await user.click(await screen.findByRole('button', { name: 'radio.settings.sites.add' }));

    // The new site is listed (its label names its language, so it is found by its feed).
    expect(await screen.findByTitle('https://site.example.org/feed/')).toBeInTheDocument();
    expect(mockApi.post).toHaveBeenLastCalledWith(
      RADIO_ENDPOINTS.sources,
      { address: 'site.example.org' },
      undefined
    );
    expect(address).toHaveValue('');
  });

  it('says why the API refused to add a site, quoting the limit it enforces', async () => {
    serve(radioOptions(), radioPreferences());
    const found: RadioDiscovery = {
      outcome: 'found',
      feed_url: 'https://site.example.org/feed/',
      title: 'Site news',
      language: 'en',
      entries: 12,
    };
    mockApi.post.mockImplementation(async (endpoint: string) => {
      if (endpoint === RADIO_ENDPOINTS.sourcePreview) return found;
      throw new ApiError('refused', 409, {
        detail: { code: 'radio_source_limit', max_sources: 1 },
      });
    });
    const { user } = renderWithProviders(<RadioSettings lng="en" />);

    await openSection(user, 'news');

    const address = await screen.findByRole('textbox', { name: 'radio.settings.sites.address' });
    await user.type(address, 'site.example.org');
    await user.click(screen.getByRole('button', { name: 'radio.settings.sites.check' }));
    await user.click(await screen.findByRole('button', { name: 'radio.settings.sites.add' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(toast.error.mock.calls[0][0]).not.toBe('radio.settings.sites.add_failed');
    expect(toast.error.mock.calls[0][0]).toMatch(/radio_source_limit/);
    expect(address).toHaveValue('site.example.org'); // nothing was added: the address stays
  });

  it('explains a rate-limited site check instead of blaming the site', async () => {
    serve(radioOptions(), radioPreferences());
    mockApi.post.mockRejectedValue(
      new ApiError('Too many requests', 429, { detail: { error: 'rate_limit_exceeded' } })
    );
    const { user } = renderWithProviders(<RadioSettings lng="en" />);
    await openSection(user, 'news');

    const address = await screen.findByRole('textbox', { name: 'radio.settings.sites.address' });
    await user.type(address, 'site.example.org');
    await user.click(screen.getByRole('button', { name: 'radio.settings.sites.check' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('radio.settings.sites.rate_limited'));
    expect(address).toHaveValue('site.example.org');
    expect(screen.queryByRole('button', { name: 'radio.settings.sites.add' })).toBeNull();
  });

  it('explains the same limit when adding a verified site', async () => {
    serve(radioOptions(), radioPreferences());
    const found: RadioDiscovery = {
      outcome: 'found',
      feed_url: 'https://site.example.org/feed/',
      title: 'Site news',
      language: 'en',
      entries: 12,
    };
    mockApi.post.mockImplementation(async (endpoint: string) => {
      if (endpoint === RADIO_ENDPOINTS.sourcePreview) return found;
      throw new ApiError('Too many requests', 429, { detail: { error: 'rate_limit_exceeded' } });
    });
    const { user } = renderWithProviders(<RadioSettings lng="en" />);
    await openSection(user, 'news');

    const address = await screen.findByRole('textbox', { name: 'radio.settings.sites.address' });
    await user.type(address, 'site.example.org');
    await user.click(screen.getByRole('button', { name: 'radio.settings.sites.check' }));
    await user.click(await screen.findByRole('button', { name: 'radio.settings.sites.add' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('radio.settings.sites.rate_limited'));
    expect(address).toHaveValue('site.example.org');
  });
});
