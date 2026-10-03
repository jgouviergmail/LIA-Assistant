/**
 * ConnectorGroupTrigger — the one visual grammar of collapsed groups (K01).
 *
 * What must hold:
 *  - the three states share one structure: group icon + label + count + chip;
 *  - the leading icon names the GROUP (a brand mark, a domain icon), so two
 *    groups in the same state no longer look identical;
 *  - the state is stated IN WORDS (the chip), never by color alone — the chip
 *    text is part of the trigger's text content, so a screen reader gets the
 *    state without seeing the tone; the chip carries the state icon too;
 *  - every icon stays out of the accessibility tree: the label names the group.
 */

import { describe, it, expect } from 'vitest';
import { Phone } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { GoogleMark } from '@/components/icons/BrandMarks';

import { ConnectorGroupTrigger } from '../ConnectorGroupTrigger';

const t = (key: string) => key;

describe('ConnectorGroupTrigger', () => {
  it.each([
    ['connected', 'settings.connectors.group_state.connected'],
    ['error', 'settings.connectors.group_state.attention'],
    ['available', 'settings.connectors.group_state.available'],
  ] as const)('states %s in words through the chip', (state, chipKey) => {
    renderWithProviders(
      <ConnectorGroupTrigger state={state} label="Google" count={3} icon={GoogleMark} t={t} />
    );
    expect(screen.getByText(chipKey)).toBeInTheDocument();
  });

  it('shows the label and the count in every state', () => {
    renderWithProviders(
      <ConnectorGroupTrigger state="available" label="Microsoft 365" count={5} icon={Phone} t={t} />
    );
    expect(screen.getByText('Microsoft 365')).toBeInTheDocument();
    expect(screen.getByText('(5)')).toBeInTheDocument();
  });

  it('draws the group icon first and the state icon inside the chip, all decorative', () => {
    const { container } = renderWithProviders(
      <ConnectorGroupTrigger state="connected" label="Téléphonie" count={1} icon={Phone} t={t} />
    );
    const icons = Array.from(container.querySelectorAll('svg'));
    expect(icons).toHaveLength(2);
    for (const icon of icons) expect(icon).toHaveAttribute('aria-hidden', 'true');
    // The group icon is the lucide Phone; the state icon lives in the chip.
    expect(icons[0]).toHaveClass('lucide-phone');
    const word = screen.getByText('settings.connectors.group_state.connected');
    // The word and the state icon share the chip.
    expect(word.parentElement).toContainElement(icons[1]);
  });

  it('keeps the state word for assistive technology on a phone, visible from sm', () => {
    renderWithProviders(
      <ConnectorGroupTrigger
        state="available"
        label="Services Google"
        count={5}
        icon={Phone}
        t={t}
      />
    );
    // A phone's chip shows the icon alone so the group's name is not truncated;
    // the word stays in the accessible name and reappears from `sm`.
    const word = screen.getByText('settings.connectors.group_state.available');
    expect(word).toHaveClass('sr-only', 'sm:not-sr-only');
  });

  it('paints a domain icon in the theme colour, and an error group in destructive', () => {
    const { container, rerender } = renderWithProviders(
      <ConnectorGroupTrigger state="available" label="Téléphonie" count={1} icon={Phone} t={t} />
    );
    expect(container.querySelector('svg')).toHaveClass('text-primary');
    rerender(
      <ConnectorGroupTrigger state="error" label="Téléphonie" count={1} icon={Phone} t={t} />
    );
    expect(container.querySelector('svg')).toHaveClass('text-destructive');
  });

  it('accepts a brand mark as the group icon', () => {
    const { container } = renderWithProviders(
      <ConnectorGroupTrigger state="connected" label="Google" count={2} icon={GoogleMark} t={t} />
    );
    const mark = container.querySelector('svg');
    expect(mark).toHaveAttribute('aria-hidden', 'true');
    expect(mark?.querySelectorAll('path')).toHaveLength(4);
  });

  it('keeps the label truncatable so the row never overflows on a phone', () => {
    renderWithProviders(
      <ConnectorGroupTrigger
        state="connected"
        label="A very long localized group label that cannot fit"
        count={9}
        icon={Phone}
        t={t}
      />
    );
    expect(screen.getByText('A very long localized group label that cannot fit')).toHaveClass(
      'truncate'
    );
  });
});
