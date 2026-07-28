/**
 * MoreContent — page body contract:
 *  - heading hierarchy: exactly one h1, one h2 per section plus the craft
 *    band, one h3 per card (26);
 *  - the hero figure is DERIVED from MORE_CARD_KEYS (never a literal);
 *  - the WCAG 2.2.2 pause toggle is present and functional;
 *  - every card carries an aria-hidden stage;
 *  - the craft band renders the maintained LANDING_STATS numbers.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LANDING_STATS } from '../../constants';
import { MORE_CARD_KEYS, MORE_SECTIONS } from '../more-data';
import { MoreContent } from '../MoreContent';

describe('MoreContent', () => {
  it('renders the full heading hierarchy: 1 h1, 7 h2, 26 h3', () => {
    render(<MoreContent lng="fr" />);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    // 6 moment sections + the craft band + the CTA block reusing landing.cta.
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(MORE_SECTIONS.length + 2);
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(MORE_CARD_KEYS.length);
  });

  it('renders one list item per card, each with an aria-hidden stage', () => {
    render(<MoreContent lng="fr" />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(MORE_CARD_KEYS.length);
    for (const item of items) {
      expect(item.querySelector('[aria-hidden="true"]')).not.toBeNull();
    }
  });

  it('derives the hero figure from the data inventory', () => {
    render(<MoreContent lng="fr" />);
    const figure = screen.getByTestId('more-hero-figure');
    expect(figure).toHaveTextContent(String(MORE_CARD_KEYS.length));
  });

  it('exposes the pause toggle and flips its pressed state', () => {
    render(<MoreContent lng="fr" />);
    const toggle = screen.getByRole('button', { name: 'more.controls.pause_animations' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders the craft band from LANDING_STATS (maintained numbers only)', () => {
    render(<MoreContent lng="fr" />);
    expect(screen.getByText(String(LANDING_STATS.uiLanguages))).toBeInTheDocument();
    expect(screen.getByText('more.craft.tests')).toBeInTheDocument();
    expect(screen.getByText('more.craft.releases')).toBeInTheDocument();
  });

  it('links the CTA to the localized register page', () => {
    // fr is the fallback locale: unprefixed path (buildLocalizedPath contract).
    render(<MoreContent lng="fr" />);
    expect(screen.getByRole('link', { name: 'landing.cta.button' })).toHaveAttribute(
      'href',
      '/register'
    );
  });

  it('prefixes the CTA for a non-fallback locale', () => {
    render(<MoreContent lng="en" />);
    expect(screen.getByRole('link', { name: 'landing.cta.button' })).toHaveAttribute(
      'href',
      '/en/register'
    );
  });
});
