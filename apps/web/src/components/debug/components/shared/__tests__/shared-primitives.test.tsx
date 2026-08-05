/**
 * Shared debug-panel primitives (v2).
 *
 * One presentation grammar for the whole panel: sections carry a themed
 * icon, empty sections are NEUTRAL (an absent optional stage is not a
 * failure), chips render through the design-system `Badge`, score bars show
 * their threshold on the bar itself, and legends derive from the single
 * score-space table.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Brain } from 'lucide-react';

import { Accordion } from '@/components/ui/accordion';
import { DebugSection } from '../DebugSection';
import { EmptySection } from '../EmptySection';
import { DebugChip } from '../DebugChip';
import { NodeChip } from '../NodeChip';
import { ScoreBar } from '../ScoreBar';
import { ScoreLegend } from '../ScoreLegend';
import { SubSectionHeader } from '../SubSectionHeader';
import { SectionBadge } from '../badges/SectionBadge';
import { ActionBadge } from '../ActionBadge';

function inOpenAccordion(value: string, ui: React.ReactNode) {
  return render(
    <Accordion type="multiple" defaultValue={[value]}>
      {ui}
    </Accordion>
  );
}

describe('DebugSection', () => {
  it('renders title, themed icon and badge slot', () => {
    inOpenAccordion(
      's1',
      <DebugSection value="s1" title="Intent Detection" icon={Brain} badge={<span>BADGE</span>}>
        <div>content</div>
      </DebugSection>
    );

    expect(screen.getByText('Intent Detection')).toBeInTheDocument();
    expect(screen.getByText('BADGE')).toBeInTheDocument();
    expect(screen.getByText('content')).toBeInTheDocument();
    // Title icon doctrine: lucide icon in the THEME colour, decorative.
    const icon = document.querySelector('svg.lucide');
    expect(icon).not.toBeNull();
    expect(icon!.getAttribute('class')).toContain('text-primary');
    expect(icon!.getAttribute('aria-hidden')).toBe('true');
  });

  it('surfaces an anomaly indicator when the section carries errors', () => {
    inOpenAccordion(
      's2',
      <DebugSection value="s2" title="Planner" anomaly>
        <div>content</div>
      </DebugSection>
    );
    expect(screen.getByTitle('This section contains an error')).toBeInTheDocument();
  });
});

describe('EmptySection', () => {
  it('renders a NEUTRAL badge — an absent stage is not a failure', () => {
    inOpenAccordion('e1', <EmptySection value="e1" title="Planner Intelligence" icon={Brain} />);

    const badge = screen.getByText('N/A');
    // Neutral secondary ground, never the destructive/fail tint.
    expect(badge.closest('[class*="destructive"]')).toBeNull();
    expect(screen.getByText('No data for this section on this request.')).toBeInTheDocument();
  });

  it('accepts a contextual message', () => {
    inOpenAccordion(
      'e2',
      <EmptySection value="e2" title="Tool Selection" message="Routed to chat — no tools involved." />
    );
    expect(screen.getByText('Routed to chat — no tools involved.')).toBeInTheDocument();
  });
});

describe('DebugChip / NodeChip', () => {
  it('renders semantic chips through Badge variants (tokens, contrast-guarded)', () => {
    render(<DebugChip tone="success">PASS</DebugChip>);
    const chip = screen.getByText('PASS');
    expect(chip.className).toContain('text-success');
  });

  it('renders node identity chips with their bi-theme family classes', () => {
    render(<NodeChip nodeName="react_call_model" />);
    const chip = screen.getByText('react_call_model');
    expect(chip.className).toContain('fuchsia');
    expect(chip.className).toContain('dark:text-fuchsia-300');
  });
});

describe('ScoreBar', () => {
  it('fills proportionally to the score with the tier tone', () => {
    render(<ScoreBar score={0.75} space="relevance" />);
    const fill = screen.getByTestId('score-bar-fill');
    expect(fill.style.width).toBe('75%');
    // 0.75 in relevance space = high tier = success token.
    expect(fill.className).toContain('bg-success');
    expect(screen.getByText('0.750')).toBeInTheDocument();
  });

  it('marks the decision threshold on the bar itself', () => {
    render(<ScoreBar score={0.3} space="relevance" threshold={0.5} />);
    const tick = screen.getByTestId('score-bar-threshold');
    expect(tick.style.left).toBe('50%');
  });

  it('renders no threshold tick when none applies', () => {
    render(<ScoreBar score={0.3} space="relevance" />);
    expect(screen.queryByTestId('score-bar-threshold')).toBeNull();
  });
});

describe('ScoreLegend', () => {
  it('derives its tier boundaries from the score-space table', () => {
    render(<ScoreLegend space="similarity" />);
    expect(screen.getByText('≥0.80')).toBeInTheDocument();
    expect(screen.getByText('0.60–0.79')).toBeInTheDocument();
    expect(screen.getByText('<0.60')).toBeInTheDocument();
  });
});

describe('SubSectionHeader', () => {
  it('renders a uniform labelled separator', () => {
    render(<SubSectionHeader label="Token Economics" />);
    expect(screen.getByText('Token Economics')).toBeInTheDocument();
  });
});

describe('SectionBadge (v2)', () => {
  it('renders PASS with the success token and the score', () => {
    render(<SectionBadge passed value={0.85} />);
    const badge = screen.getByLabelText('Status: PASS 85%');
    expect(badge.className).toContain('text-success');
    expect(badge.textContent).toContain('85%');
  });

  it('renders FAIL with the destructive token', () => {
    render(<SectionBadge passed={false} value={0.12} />);
    expect(screen.getByLabelText('Status: FAIL 12%').className).toContain('text-destructive');
  });
});

describe('ConfidenceBadge / ZoneBadge / StrategyBadge (v2)', () => {
  it('renders confidence levels with semantic tokens', async () => {
    const { ConfidenceBadge } = await import('../badges/ConfidenceBadge');
    render(<ConfidenceBadge confidence="high" />);
    expect(screen.getByLabelText('Confidence: high').className).toContain('text-success');
  });

  it('renders the emergency zone as the only solid fill', async () => {
    const { ZoneBadge } = await import('../badges/ZoneBadge');
    render(<ZoneBadge zone="emergency" />);
    const badge = screen.getByLabelText('Zone: emergency');
    expect(badge.className).toContain('bg-destructive ');
    expect(badge.className).toContain('text-destructive-foreground');
  });

  it('renders strategies with their degradation tone and short label', async () => {
    const { StrategyBadge } = await import('../badges/StrategyBadge');
    render(<StrategyBadge strategy="panic_mode" />);
    const badge = screen.getByLabelText('Strategy: panic_mode');
    expect(badge.textContent).toBe('Panic');
    expect(badge.className).toContain('text-destructive');
  });
});

describe('ActionBadge (v2)', () => {
  it.each([
    ['create', 'CREATE', 'text-success'],
    ['create_new', 'CREATE', 'text-success'],
    ['update', 'UPDATE', 'text-warning'],
    ['consolidate', 'MERGE', 'text-primary'],
    ['delete', 'DELETE', 'text-destructive'],
  ])('renders %s as %s with its tone token', (action, label, token) => {
    render(<ActionBadge action={action} />);
    const badge = screen.getByText(label);
    expect(badge.className).toContain(token);
  });

  it('falls back to a neutral chip for unknown actions', () => {
    render(<ActionBadge action="mystify" />);
    const badge = screen.getByText('MYSTIFY');
    expect(badge.className).not.toContain('text-success');
  });
});
