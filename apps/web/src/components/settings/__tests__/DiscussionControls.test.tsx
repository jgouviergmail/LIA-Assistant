/**
 * The discussion controls' two lists of switches read alike (owner request
 * 2026-10-21): « Données autorisées » and « Sujets sensibles » are panels on
 * the card ground inside their folds, the topics in a single column.
 */

import { describe, it, expect, vi } from 'vitest';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { DiscussionControls } from '../DiscussionControls';
import { discussionTopics, type DiscussionSettings } from '@/types/proactive-discussions';

const settings: DiscussionSettings = {
  policy: {
    enabled: true,
    start_hour: 9,
    end_hour: 20,
    timezone: 'Europe/Paris',
    daily_max: 2,
    sources: ['sms'],
    sensitive_topics: ['health'],
    forbidden_topics: ['travail'],
    paused_until: null,
    revision: 1,
  },
  sources: [
    { key: 'sms', operations: ['list'], indivisible: false, dependencies: [] },
    { key: 'reminders', operations: ['list'], indivisible: false, dependencies: [] },
  ],
  producer_enabled: true,
  budget_configured: true,
  pause_hours: 4,
};

function unfold(title: string) {
  const details = screen.getByText(title, { selector: 'summary span' }).closest('details');
  if (!details) throw new Error(`no fold ${title}`);
  act(() => {
    details.open = true;
    details.dispatchEvent(new Event('toggle'));
  });
}

function panelOf(control: HTMLElement): HTMLElement {
  const panel = control.closest<HTMLElement>('div.rounded-lg');
  if (!panel) throw new Error('the control has no panel');
  return panel;
}

describe('DiscussionControls', () => {
  it('draws every allowed source as a panel on the card ground', async () => {
    renderWithProviders(
      <DiscussionControls lng="fr" settings={settings} busy={false} update={vi.fn()} />
    );
    unfold('discussions.sources_title');

    for (const key of ['sms', 'reminders']) {
      const control = await screen.findByRole('switch', { name: `discussions.sources.${key}` });
      expect(panelOf(control)).toHaveClass('border', 'bg-card');
    }
  });

  it('draws the sensitive topics like the sources, one per line', async () => {
    const update = vi.fn().mockResolvedValue(undefined);
    const { user } = renderWithProviders(
      <DiscussionControls lng="fr" settings={settings} busy={false} update={update} />
    );
    unfold('discussions.topics_title');

    const switches = await Promise.all(
      discussionTopics.map(topic =>
        screen.findByRole('switch', { name: `discussions.topics.${topic}` })
      )
    );
    const panels = switches.map(panelOf);
    for (const panel of panels) expect(panel).toHaveClass('border', 'bg-card');
    // One column: the topics' list never splits in two.
    expect(panels[0].parentElement).not.toHaveClass('sm:grid-cols-2');

    await user.click(switches[1]);
    expect(update).toHaveBeenCalledExactlyOnceWith({
      sensitive_topics: ['health', 'relationships'],
    });
  });
});
