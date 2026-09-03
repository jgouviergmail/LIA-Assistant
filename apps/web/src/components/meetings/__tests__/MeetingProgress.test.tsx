import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { MeetingProgress } from '../MeetingProgress';

describe('MeetingProgress', () => {
  it('marks the current stage and lists the four stages in order', () => {
    renderWithProviders(<MeetingProgress lng="en" status="processing" stage="synthesizing" />);
    const items = screen.getAllByRole('listitem');
    expect(items.map(item => item.textContent)).toEqual([
      'meetings.stage.normalizing',
      'meetings.stage.transcribing',
      'meetings.stage.synthesizing',
      'meetings.stage.indexing',
    ]);
    expect(items[2]).toHaveAttribute('aria-current', 'step');
    expect(items[0]).not.toHaveAttribute('aria-current');
  });

  it('a queued meeting shows the first stage as active', () => {
    renderWithProviders(<MeetingProgress lng="en" status="stopped" stage={null} />);
    expect(screen.getAllByRole('listitem')[0]).toHaveAttribute('aria-current', 'step');
  });

  it('a ready meeting has no active stage left', () => {
    renderWithProviders(<MeetingProgress lng="en" status="ready" stage={null} />);
    expect(screen.queryByRole('listitem', { current: 'step' })).not.toBeInTheDocument();
  });
});
