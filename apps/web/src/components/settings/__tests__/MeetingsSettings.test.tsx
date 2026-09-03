/**
 * The meetings settings section (ADR-258, library ADR-259): gated on the
 * instance flag, preferences saved only when dirty — the default minutes
 * format among them — the library reachable from a summary block, recent
 * meetings linked.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingPreferences, MeetingSummary, MeetingTemplateSummary } from '@/types/meetings';

const flags = vi.hoisted(() => ({ enabled: true, loading: false }));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { meetings_enabled: flags.enabled } },
    loading: flags.loading,
    error: null,
  }),
}));

const prefs = vi.hoisted(() => ({
  save: vi.fn(),
  value: null as MeetingPreferences | null,
}));
vi.mock('@/hooks/useMeetingPreferences', () => ({
  useMeetingPreferences: () => ({
    preferences: prefs.value,
    isLoading: prefs.value === null,
    isSaving: false,
    error: null,
    save: prefs.save,
  }),
}));

const library = vi.hoisted(() => ({
  templates: [] as MeetingTemplateSummary[],
  maxUserTemplates: 50,
  isLoading: false,
}));
vi.mock('@/hooks/useMeetingTemplates', () => ({
  useMeetingTemplates: () => ({
    templates: library.templates,
    maxUserTemplates: library.maxUserTemplates,
    isLoading: library.isLoading,
    isSaving: false,
    error: null,
    refetch: vi.fn(),
    load: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  }),
}));

const list = vi.hoisted(() => ({ meetings: [] as MeetingSummary[], total: 0 }));
vi.mock('@/hooks/useMeetings', () => ({
  useMeetingList: () => ({
    meetings: list.meetings,
    total: list.total,
    isLoading: false,
    isUnavailable: false,
    error: null,
    refetch: vi.fn(),
    isDeleting: false,
    bulkDelete: vi.fn(),
  }),
}));

const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { MeetingsSettings } from '../MeetingsSettings';

function preferences(over: Partial<MeetingPreferences> = {}): MeetingPreferences {
  return {
    stt_engine: 'auto',
    language: 'auto',
    auto_email: false,
    keep_audio_hours: 0,
    default_template_ref: null,
    keep_audio_hours_max: 168,
    ...over,
  };
}

function summary(over: Partial<MeetingTemplateSummary> = {}): MeetingTemplateSummary {
  return {
    ref: 'builtin:default_minutes',
    name: 'Meeting minutes',
    description: null,
    category: 'meeting',
    builtin: true,
    sections_count: 6,
    auto_selectable: true,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  flags.enabled = true;
  flags.loading = false;
  prefs.value = preferences();
  prefs.save.mockResolvedValue(preferences());
  library.templates = [
    summary(),
    summary({ ref: 'builtin:daily_standup', name: 'Daily' }),
    summary({ ref: 'user:1', name: 'Mine', category: 'custom', builtin: false }),
  ];
  library.isLoading = false;
  list.meetings = [];
  list.total = 0;
});

describe('MeetingsSettings', () => {
  it('renders nothing when the instance flag is off', () => {
    flags.enabled = false;
    const { container } = renderWithProviders(<MeetingsSettings lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the section with its three blocks and the library summary', () => {
    renderWithProviders(<MeetingsSettings lng="en" />);
    expect(screen.getByRole('heading', { name: 'settings.meetings.title' })).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.preferences_title')).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.templates_title')).toBeInTheDocument();
    // The count states the user's own templates (one here), never the built-ins.
    expect(screen.getByText('meetings.settings.templates_count')).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.no_meetings')).toBeInTheDocument();
  });

  it('offers the default minutes format, automatic first, and names the chosen one', () => {
    prefs.value = preferences({ default_template_ref: 'builtin:daily_standup' });
    renderWithProviders(<MeetingsSettings lng="en" />);
    const trigger = screen.getByRole('combobox', {
      name: 'meetings.settings.default_template_label',
    });
    expect(trigger).toHaveTextContent('Daily');
    expect(screen.getByText('meetings.settings.default_template_hint')).toBeInTheDocument();
  });

  it('saves the preferences only once something changed, the default format included', async () => {
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    const savePrefs = screen.getByRole('button', { name: 'common.save' });
    expect(savePrefs).toHaveAttribute('aria-disabled', 'true');
    await user.click(savePrefs);
    expect(prefs.save).not.toHaveBeenCalled();

    await user.click(screen.getByRole('switch', { name: 'meetings.settings.auto_email_label' }));
    expect(savePrefs).toHaveAttribute('aria-disabled', 'false');
    await user.click(savePrefs);
    expect(prefs.save).toHaveBeenCalledWith({
      stt_engine: 'auto',
      language: 'auto',
      auto_email: true,
      keep_audio_hours: 0,
      default_template_ref: null,
    });
  });

  it('clamps the audio retention to the admin ceiling', async () => {
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    const hours = screen.getByLabelText('meetings.settings.keep_audio_label');
    await user.clear(hours);
    await user.type(hours, '999');
    expect(hours).toHaveValue(168);
  });

  it('opens the library page from the templates block', async () => {
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'meetings.settings.manage_templates' }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/templates');
  });

  it('links each recent meeting to its page', async () => {
    list.meetings = [
      {
        id: 'm1',
        status: 'ready',
        stage: null,
        title: 'Point projet',
        started_at: '2026-09-02T10:00:00Z',
        stopped_at: null,
        audio_duration_seconds: 125,
        participants_count: 2,
        action_items_count: 1,
        index_state: 'indexed',
        stt_provider: 'elevenlabs',
        total_cost_eur: null,
        last_error_code: null,
        template_ref: null,
        template_name: null,
        template_selection: null,
        source_meeting_id: null,
      },
    ];
    list.total = 1;
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Point projet' }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/m1');
    await user.click(screen.getByRole('button', { name: /meetings\.settings\.view_all/ }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings');
  });
});
