/**
 * OpenLoopExtractionSection — debug panel section for the background
 * commitments-ledger extraction (ADR-139).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Accordion } from '@/components/ui/accordion';
import { OpenLoopExtractionSection } from '../OpenLoopExtractionSection';
import type { OpenLoopExtractionMetrics } from '@/types/chat';

function renderSection(data: OpenLoopExtractionMetrics | undefined) {
  return render(
    <Accordion type="multiple" defaultValue={['open-loop-extraction']}>
      <OpenLoopExtractionSection data={data} />
    </Accordion>
  );
}

const METRICS: OpenLoopExtractionMetrics = {
  items_parsed: 2,
  opened: 1,
  closed: 1,
  skipped: 0,
  items: [
    {
      action: 'open',
      subject: 'envoyer le devis à Marie',
      direction: 'user_owes',
      counterparty: 'Marie',
      due_hint_iso: '2026-07-25T18:00:00+02:00',
    },
    {
      action: 'close',
      subject: 'rappeler le plombier',
      direction: 'user_owes',
      counterparty: null,
      due_hint_iso: null,
    },
  ],
};

describe('OpenLoopExtractionSection', () => {
  it('renders the applied/parsed badge and every proposed item', () => {
    renderSection(METRICS);

    expect(screen.getByText('Open Loop Extraction')).toBeInTheDocument();
    // applied = opened + closed = 2, parsed = 2
    expect(screen.getByText('2/2')).toBeInTheDocument();
    expect(screen.getByText('envoyer le devis à Marie')).toBeInTheDocument();
    expect(screen.getByText('rappeler le plombier')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
    expect(screen.getByText('2026-07-25T18:00:00+02:00')).toBeInTheDocument();
  });

  it('renders the empty placeholder without data', () => {
    renderSection(undefined);

    expect(screen.getByText('Open Loop Extraction')).toBeInTheDocument();
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('shows the no-commitments message when nothing was proposed', () => {
    renderSection({ items_parsed: 0, opened: 0, closed: 0, skipped: 0, items: [] });

    expect(screen.getByText('No commitments detected in this turn.')).toBeInTheDocument();
  });
});
