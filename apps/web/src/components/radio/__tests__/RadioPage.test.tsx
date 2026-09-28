/**
 * The radio's page (ADR-324): the start sends only what the listener changed
 * for this session; on air, the transcript follows the audio, shows where each
 * sentence comes from — never a link that is not a web address — and names
 * what comes next.
 */

import { act, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { RadioSegment } from '@/lib/radio/types';
import { IDLE_RADIO_VIEW, useRadioStore } from '@/stores/radioStore';

const player = vi.hoisted(() => ({
  start: vi.fn(async () => undefined),
  position: vi.fn(() => 0),
}));
vi.mock('@/lib/radio/player', () => ({ radioPlayer: () => player }));

import { RadioPage, startOptions } from '../RadioPage';
import { RadioTranscript } from '../RadioTranscript';

const SEGMENT: RadioSegment = {
  seq: 3,
  format: 'brief',
  mood: 'news',
  title: 'Rain over the capital',
  duration_s: 40,
  transcript: [
    { role: 'host', text: 'Here is the news.', offset_s: 1, sources: [] },
    {
      role: 'anchor',
      text: 'Rain is expected.',
      offset_s: 4,
      sources: [
        {
          label: 'Example News',
          url: 'https://news.example/rain',
          published_at: null,
          article_id: 'story-rain',
        },
        {
          label: 'Hostile Feed',
          url: 'javascript:alert(1)',
          published_at: null,
          article_id: null,
        },
      ],
    },
    { role: 'host', text: 'That was the brief.', offset_s: 30, sources: [] },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  useRadioStore.getState().setView(IDLE_RADIO_VIEW);
});

describe('startOptions', () => {
  it('sends only what the listener changed for this session', () => {
    expect(startOptions('default', false)).toEqual({});
    expect(startOptions('15', true)).toEqual({ timer_minutes: 15, public_mode: true });
    expect(startOptions('0', false)).toEqual({ timer_minutes: 0 });
  });
});

describe('RadioPage', () => {
  it('starts the station from its button, with the listener’s settings by default', () => {
    renderWithProviders(<RadioPage lng="en" available />);
    fireEvent.click(screen.getByRole('button', { name: 'radio.page.start' }));
    expect(player.start).toHaveBeenCalledWith({});
  });

  it('turns into the programme on air, and names what comes next', () => {
    renderWithProviders(<RadioPage lng="en" available />);
    act(() =>
      useRadioStore.getState().setView({
        ...IDLE_RADIO_VIEW,
        status: 'playing',
        sessionId: 's1',
        current: SEGMENT,
        next: { ...SEGMENT, seq: 4, format: 'bulletin', title: 'The news' },
      })
    );
    expect(screen.queryByRole('button', { name: 'radio.page.start' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Rain over the capital' })).toBeInTheDocument();
    expect(screen.getByText('radio.page.next')).toBeInTheDocument();
  });

  it('says the next programme is on its way while nothing is on air yet', () => {
    renderWithProviders(<RadioPage lng="en" available />);
    act(() =>
      useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'waiting', sessionId: 's1' })
    );
    expect(screen.getByText('radio.page.between_programmes')).toBeInTheDocument();
  });

  it('says the radio is not offered, and offers no start, where the instance does not', () => {
    renderWithProviders(<RadioPage lng="en" available={false} />);
    expect(screen.getByText('radio.page.unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'radio.page.start' })).not.toBeInTheDocument();
  });

  it('neither offers nor refuses while the configuration loads', () => {
    renderWithProviders(<RadioPage lng="en" available={null} />);
    expect(screen.queryByRole('button', { name: 'radio.page.start' })).not.toBeInTheDocument();
    expect(screen.queryByText('radio.page.unavailable')).not.toBeInTheDocument();
  });

  it('lists the articles the session cited, and keeps them once it is over', () => {
    renderWithProviders(<RadioPage lng="en" available />);
    const articles = [
      {
        id: 'story-rain',
        outlet: 'Example News',
        url: 'https://news.example/rain',
        publishedAt: null,
      },
    ];
    act(() =>
      useRadioStore.getState().setView({
        ...IDLE_RADIO_VIEW,
        status: 'playing',
        sessionId: 's1',
        current: SEGMENT,
        articles,
      })
    );
    const section = screen.getByRole('region', { name: 'radio.article.section_title' });
    expect(within(section).getByText('Example News')).toBeInTheDocument();

    act(() => useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'ended', articles }));
    expect(screen.getByRole('button', { name: 'radio.page.start' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'radio.article.section_title' })).toBeInTheDocument();
  });

  it('follows a session already on air to its end, the switch turned off meanwhile', () => {
    renderWithProviders(<RadioPage lng="en" available={false} />);
    act(() =>
      useRadioStore.getState().setView({ ...IDLE_RADIO_VIEW, status: 'waiting', sessionId: 's1' })
    );
    expect(screen.getByText('radio.page.between_programmes')).toBeInTheDocument();
    expect(screen.queryByText('radio.page.unavailable')).not.toBeInTheDocument();
  });
});

describe('RadioTranscript', () => {
  it('marks the line being spoken', () => {
    renderWithProviders(<RadioTranscript lng="en" segment={SEGMENT} positionS={5} />);
    const lines = within(screen.getByRole('list')).getAllByRole('listitem');
    expect(lines.map(line => line.getAttribute('aria-current'))).toEqual([null, 'true', null]);
  });

  it('links a web source, and never a source that is not a web address', () => {
    renderWithProviders(<RadioTranscript lng="en" segment={SEGMENT} positionS={0} />);
    expect(screen.getByRole('link', { name: /Example News/ })).toHaveAttribute(
      'href',
      'https://news.example/rain'
    );
    expect(screen.getByRole('link', { name: /Example News/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer'
    );
    expect(screen.queryByRole('link', { name: /Hostile Feed/ })).not.toBeInTheDocument();
    expect(screen.getByText('Hostile Feed')).toBeInTheDocument();
  });
});
