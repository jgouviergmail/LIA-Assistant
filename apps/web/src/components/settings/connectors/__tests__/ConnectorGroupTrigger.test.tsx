/**
 * ConnectorGroupTrigger — the one visual grammar of collapsed groups (K01).
 *
 * What must hold:
 *  - the three states share one structure: icon + label + count + state chip;
 *  - the state is stated IN WORDS (the chip), never by color alone — the chip
 *    text is part of the trigger's text content, so a screen reader gets the
 *    state without seeing the tone;
 *  - decorative glyphs (💡, 📞) and the state icon stay out of the
 *    accessibility tree.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { ConnectorGroupTrigger } from '../ConnectorGroupTrigger';

const t = (key: string) => key;

describe('ConnectorGroupTrigger', () => {
  it.each([
    ['connected', 'settings.connectors.group_state.connected'],
    ['error', 'settings.connectors.group_state.attention'],
    ['available', 'settings.connectors.group_state.available'],
  ] as const)('states %s in words through the chip', (state, chipKey) => {
    renderWithProviders(<ConnectorGroupTrigger state={state} label="Google" count={3} t={t} />);
    expect(screen.getByText(chipKey)).toBeInTheDocument();
  });

  it('shows the label and the count in every state', () => {
    renderWithProviders(
      <ConnectorGroupTrigger state="available" label="Microsoft 365" count={5} t={t} />
    );
    expect(screen.getByText('Microsoft 365')).toBeInTheDocument();
    expect(screen.getByText('(5)')).toBeInTheDocument();
  });

  it('keeps the state icon decorative', () => {
    const { container } = renderWithProviders(
      <ConnectorGroupTrigger state="connected" label="Google" count={1} t={t} />
    );
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the domain glyph decorative', () => {
    renderWithProviders(
      <ConnectorGroupTrigger state="connected" label="Téléphonie" count={1} glyph="📞" t={t} />
    );
    expect(screen.getByText('📞')).toHaveAttribute('aria-hidden', 'true');
  });
});
