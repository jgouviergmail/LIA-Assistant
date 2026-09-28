/**
 * What each choice of the radio's settings says it covers: every programme and
 * personal source carries a description its control points at, and the figures
 * in it are the API's.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseRadioSourcesReturn } from '@/hooks/useRadioSources';
import {
  radioOptions,
  radioOwnSource,
  radioPreferences,
  radioSources,
} from '@/lib/radio/__tests__/fixtures';
import { RadioCustomSources } from '../RadioCustomSources';
import { RadioProgrammeFields } from '../RadioProgrammeFields';
import { RadioSourceFields } from '../RadioSourceFields';

// The global stub echoes the key alone: here the parameters are echoed too, so
// the figures a description is given can be read back.
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

const noop = () => undefined;

/** The newsroom a site list is handed: what the API counted, and writes that succeed. */
function newsroomOf(over: Partial<UseRadioSourcesReturn> = {}): UseRadioSourcesReturn {
  return {
    sources: radioSources(),
    preview: vi.fn(async () => ({ ok: false as const, refusal: null })),
    add: vi.fn(async () => ({ ok: false as const, refusal: null })),
    remove: vi.fn(async () => true),
    change: vi.fn(async () => true),
    forget: vi.fn(async () => true),
    refresh: vi.fn(async () => undefined),
    busy: false,
    ...over,
  };
}

describe('the description under every choice', () => {
  it('names what each programme covers with the figures the API enforces', async () => {
    const { user } = renderWithProviders(
      <RadioProgrammeFields
        lng="en"
        options={radioOptions()}
        preferences={radioPreferences()}
        onChange={noop}
      />
    );
    await user.click(screen.getByText('radio.settings.programmes.title'));
    expect(
      screen.getByRole('combobox', { name: 'radio.formats.headlines' })
    ).toHaveAccessibleDescription(
      'radio.settings.programmes.hints.headlines {"stories":5,"noon":12,"evening":18}'
    );
  });

  it('says what each personal source reads', async () => {
    const { user } = renderWithProviders(
      <RadioSourceFields
        lng="en"
        options={radioOptions()}
        preferences={radioPreferences()}
        onChange={noop}
      />
    );
    await user.click(screen.getByText('radio.settings.sources.title'));
    expect(
      screen.getByRole('switch', { name: 'radio.settings.source.health' })
    ).toHaveAccessibleDescription('radio.settings.source_hints.health');
  });

  it('says what each site holds for the listener, as the API counted it', () => {
    const own = [
      radioOwnSource({ id: 'a', title: 'Running', language: null, stories: 4, unheard: 1 }),
      radioOwnSource({ id: 'b', title: 'Resting', language: null, paused: true, failing: true }),
    ];
    renderWithProviders(
      <RadioCustomSources
        lng="en"
        newsroom={newsroomOf({ sources: radioSources({ own }) })}
        max={20}
        addressMax={2048}
        titleMax={120}
      />
    );
    expect(screen.getByRole('checkbox', { name: 'Running' })).toHaveAccessibleDescription(
      'radio.settings.news.counts {"stories":4,"unheard":1}'
    );
    // A paused site reads nothing: it says so, and still says it was failing.
    expect(screen.getByRole('checkbox', { name: 'Resting' })).toHaveAccessibleDescription(
      'radio.settings.sites.paused radio.settings.news.failing'
    );
  });
});
