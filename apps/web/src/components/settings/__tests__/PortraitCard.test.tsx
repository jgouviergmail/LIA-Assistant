/**
 * PortraitCard — the compiled portrait in its two formats, drawn only when
 * there is one, its provenance under it (ADR-292), and the one lever the card
 * offers. Extracted from JournalsSettings under the complexity ratchet; the
 * behaviours below are the ones the section used to carry inline.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, userEvent } from '@/__tests__/test-utils';
import type { JournalPortrait } from '@/hooks/useJournals';

import { PortraitCard } from '../PortraitCard';

function portrait(over: Partial<JournalPortrait> = {}): JournalPortrait {
  return {
    full: 'A person who plans in the evening.',
    brief: 'Plans in the evening.',
    compiled_at: '2026-09-17T08:00:00Z',
    sources: {
      version: 1,
      journal_entries: 3,
      sources: {
        memories: { status: 'used', used: 2, total: 2 },
        interests: { status: 'empty', used: 0, total: 0 },
        habits: { status: 'disabled', used: 0, total: 0 },
        relation_debriefs: { status: 'used', used: 1, total: 1 },
      },
    },
    ...over,
  };
}

const props = {
  lng: 'en' as const,
  formatRelativeDate: (iso: string | null) => (iso ? 'today' : 'never'),
  onSignal: vi.fn(),
  signalDisabled: false,
};

describe('PortraitCard', () => {
  it('draws nothing when no portrait was compiled', () => {
    const { container } = renderWithProviders(<PortraitCard {...props} portrait={null} />);
    expect(container).toBeEmptyDOMElement();
    const empty = portrait({ full: null, brief: null });
    const second = renderWithProviders(<PortraitCard {...props} portrait={empty} />);
    expect(second.container).toBeEmptyDOMElement();
  });

  it('shows the full portrait first and switches to the brief one on demand', async () => {
    renderWithProviders(<PortraitCard {...props} portrait={portrait()} />);
    expect(screen.getByText('A person who plans in the evening.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'journals.portraitFormatBrief' }));
    expect(screen.getByText('Plans in the evening.')).toBeInTheDocument();
    expect(screen.queryByText('A person who plans in the evening.')).not.toBeInTheDocument();
  });

  it('disables a format the portrait does not have', () => {
    renderWithProviders(<PortraitCard {...props} portrait={portrait({ brief: null })} />);
    expect(screen.getByRole('button', { name: 'journals.portraitFormatBrief' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'journals.portraitFormatFull' })).toBeEnabled();
  });

  it('draws the provenance under the words and offers the signal lever', async () => {
    const onSignal = vi.fn();
    renderWithProviders(<PortraitCard {...props} portrait={portrait()} onSignal={onSignal} />);
    expect(screen.getByTestId('portrait-provenance').getAttribute('data-parts')).toBe(
      'entries:3|memories:2|relation_debriefs:1'
    );
    await userEvent.click(screen.getByRole('button', { name: 'journals.portraitFeedbackButton' }));
    expect(onSignal).toHaveBeenCalledTimes(1);
  });

  it('omits the provenance line before the first compilation with sources', () => {
    renderWithProviders(<PortraitCard {...props} portrait={portrait({ sources: null })} />);
    expect(screen.queryByTestId('portrait-provenance')).not.toBeInTheDocument();
  });
});
