/**
 * The meetings settings section: gated on the instance flag, preferences saved
 * only when dirty, the template editable and restorable, recent meetings linked.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingPreferences, MeetingSummary, MeetingTemplate } from '@/types/meetings';

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

const tpl = vi.hoisted(() => ({
  save: vi.fn(),
  reset: vi.fn(),
  value: null as MeetingTemplate | null,
}));
vi.mock('@/hooks/useMeetingTemplate', () => ({
  useMeetingTemplate: () => ({
    template: tpl.value,
    isLoading: tpl.value === null,
    isSaving: false,
    error: null,
    refetch: vi.fn(),
    save: tpl.save,
    reset: tpl.reset,
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
  }),
}));

const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { MeetingsSettings } from '../MeetingsSettings';

function preferences(): MeetingPreferences {
  return {
    stt_engine: 'auto',
    language: 'auto',
    auto_email: false,
    keep_audio_hours: 0,
    keep_audio_hours_max: 168,
  };
}

function template(): MeetingTemplate {
  return {
    id: null,
    name: 'Default minutes',
    is_builtin_default: true,
    sections: [{ key: 'summary', label: 'Summary', instruction: 'Prose.', kind: 'paragraph' }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  flags.enabled = true;
  flags.loading = false;
  prefs.value = preferences();
  prefs.save.mockResolvedValue(preferences());
  tpl.value = template();
  tpl.save.mockResolvedValue(template());
  tpl.reset.mockResolvedValue(template());
  list.meetings = [];
  list.total = 0;
});

describe('MeetingsSettings', () => {
  it('renders nothing when the instance flag is off', () => {
    flags.enabled = false;
    const { container } = renderWithProviders(<MeetingsSettings lng="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the section with its three blocks and the default template badge', () => {
    renderWithProviders(<MeetingsSettings lng="en" />);
    expect(screen.getByRole('heading', { name: 'settings.meetings.title' })).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.preferences_title')).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.template_title')).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.template_builtin_badge')).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.no_meetings')).toBeInTheDocument();
  });

  it('saves the preferences only once something changed', async () => {
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    const [savePrefs] = screen.getAllByRole('button', { name: 'common.save' });
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
    });
  });

  it('clamps the audio retention to the admin ceiling', async () => {
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    const hours = screen.getByLabelText('meetings.settings.keep_audio_label');
    await user.clear(hours);
    await user.type(hours, '999');
    expect(hours).toHaveValue(168);
  });

  it('saves an edited template and restores the default', async () => {
    const { user } = renderWithProviders(<MeetingsSettings lng="en" />);
    const name = screen.getByLabelText('meetings.settings.template_name_label');
    await user.type(name, ' v2');
    const [, saveTemplate] = screen.getAllByRole('button', { name: 'common.save' });
    await user.click(saveTemplate);
    expect(tpl.save).toHaveBeenCalledWith({
      name: 'Default minutes v2',
      sections: template().sections,
    });
    await user.click(screen.getByRole('button', { name: 'meetings.settings.reset_template' }));
    expect(tpl.reset).toHaveBeenCalledTimes(1);
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
