import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { isMeetingNotificationMetadata } from '@/types/meetings';

const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

import { MeetingMinutesCard, costLabel, hasCostFacts } from '../MeetingMinutesCard';

const metadata = {
  type: 'proactive_meeting' as const,
  target_id: 'm1',
  meeting_id: 'm1',
  title: 'Point projet',
  duration_seconds: 3725,
  participants_count: 3,
  action_items_count: 2,
  gaps: 1,
};

describe('MeetingMinutesCard', () => {
  it('shows the duration and counts, the gap notice, and opens the minutes', async () => {
    const { user } = renderWithProviders(<MeetingMinutesCard lng="en" metadata={metadata} />);
    // The i18n stub returns keys; the duration is formatted by the component.
    expect(
      screen.getByText('1:02:05 · meetings.list.participants · meetings.list.actions')
    ).toBeInTheDocument();
    expect(screen.getByText('meetings.detail.gaps_notice')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /meetings\.card\.open/ }));
    expect(push).toHaveBeenCalledWith('/dashboard/meetings/m1');
  });

  it('shows no gap notice for a clean recording', () => {
    renderWithProviders(<MeetingMinutesCard lng="en" metadata={{ ...metadata, gaps: 0 }} />);
    expect(screen.queryByText('meetings.detail.gaps_notice')).not.toBeInTheDocument();
  });
});

describe('isMeetingNotificationMetadata', () => {
  it('accepts the dispatcher payload and rejects other proactive types', () => {
    expect(isMeetingNotificationMetadata(metadata)).toBe(true);
    expect(isMeetingNotificationMetadata({ ...metadata, type: 'proactive_interest' })).toBe(false);
    expect(isMeetingNotificationMetadata({ type: 'proactive_meeting' })).toBe(false);
    expect(isMeetingNotificationMetadata(null)).toBe(false);
  });
});

describe('MeetingMinutesCard — costs (ADR-258)', () => {
  const priced = {
    ...metadata,
    tokens_in: 1200,
    tokens_out: 300,
    tokens_cache: 0,
    model_name: 'gpt-4.1',
    stt_cost_eur: 0.0046,
    stt_audio_duration_seconds: 53.3,
    llm_cost_eur: 0.0121,
    cost_eur: 0.0167,
  };

  it('states both paid units and their sum when the user displays costs', () => {
    renderWithProviders(<MeetingMinutesCard lng="en" metadata={priced} showCosts />);
    expect(screen.getByTestId('meeting-card-costs')).toHaveTextContent('meetings.card.cost_line');
  });

  it('stays silent about costs when the preference is off or nothing is priced', () => {
    renderWithProviders(<MeetingMinutesCard lng="en" metadata={priced} />);
    expect(screen.queryByTestId('meeting-card-costs')).not.toBeInTheDocument();
    renderWithProviders(<MeetingMinutesCard lng="en" metadata={metadata} showCosts />);
    expect(screen.queryByTestId('meeting-card-costs')).not.toBeInTheDocument();
  });

  it('formats a known amount and names an unknown price instead of writing zero', () => {
    expect(costLabel(0.0046, 'en', 'not priced')).toBe('€0.0046');
    expect(costLabel(0, 'fr', 'non tarifé')).toBe('0,0000 €');
    expect(costLabel(null, 'en', 'not priced')).toBe('not priced');
    expect(costLabel(undefined, 'en', 'not priced')).toBe('not priced');
    expect(hasCostFacts(metadata)).toBe(false);
    expect(hasCostFacts({ ...metadata, stt_cost_eur: null })).toBe(true);
  });
});

