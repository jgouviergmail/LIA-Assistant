/**
 * QuickAccessCompact — the compact Help + Settings bar above the briefing.
 *
 * What must hold, in order of consequence:
 *  1. both destinations are reachable, in a stable order, and land on the right
 *     localized URL — this component's whole purpose is findability;
 *  2. they are LINKS, not buttons: middle-click, open-in-new-tab and the "link"
 *     role are what a navigation owes its user (the previous implementation
 *     used `<button onClick={router.push}>`);
 *  3. every label AND its subline survive the compaction — the bar was made
 *     denser, not more silent;
 *  4. an anchor contains phrasing content only. The former card nested `<div>`s
 *     inside a `<button>`, which is invalid HTML; the rewrite must not carry
 *     that over to `<a>`.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { QuickAccessCompact } from '../QuickAccessCompact';

/** The global i18n stub echoes keys, so labels ARE their keys here. */
const HELP = 'dashboard.quick_access_compact.help';
const HELP_SUB = 'dashboard.quick_access_compact.help_sub';
const SETTINGS = 'dashboard.quick_access_compact.settings';
const SETTINGS_SUB = 'dashboard.quick_access_compact.settings_sub';

describe('QuickAccessCompact', () => {
  it('offers exactly two destinations, help first', () => {
    renderWithProviders(<QuickAccessCompact lng="fr" />);

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAccessibleName(new RegExp(HELP));
    expect(links[1]).toHaveAccessibleName(new RegExp(SETTINGS));
  });

  it('links to the localized FAQ and settings pages', () => {
    renderWithProviders(<QuickAccessCompact lng="fr" />);

    expect(screen.getByRole('link', { name: new RegExp(HELP) })).toHaveAttribute(
      'href',
      '/fr/dashboard/faq'
    );
    expect(screen.getByRole('link', { name: new RegExp(SETTINGS) })).toHaveAttribute(
      'href',
      '/fr/dashboard/settings'
    );
  });

  it('honours the current locale in both links', () => {
    renderWithProviders(<QuickAccessCompact lng="de" />);

    expect(screen.getByRole('link', { name: new RegExp(HELP) })).toHaveAttribute(
      'href',
      '/de/dashboard/faq'
    );
    expect(screen.getByRole('link', { name: new RegExp(SETTINGS) })).toHaveAttribute(
      'href',
      '/de/dashboard/settings'
    );
  });

  it('keeps both sublines — density must not cost information', () => {
    renderWithProviders(<QuickAccessCompact lng="fr" />);

    const help = screen.getByRole('link', { name: new RegExp(HELP) });
    expect(within(help).getByText(HELP_SUB)).toBeInTheDocument();

    const settings = screen.getByRole('link', { name: new RegExp(SETTINGS) });
    expect(within(settings).getByText(SETTINGS_SUB)).toBeInTheDocument();
  });

  it('navigates with anchors, never with buttons', () => {
    renderWithProviders(<QuickAccessCompact lng="fr" />);

    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('puts only phrasing content inside each anchor (valid HTML)', () => {
    const { container } = renderWithProviders(<QuickAccessCompact lng="fr" />);

    // `<a>` accepts phrasing content only: a div/p/heading inside it is invalid
    // markup, which is exactly what the previous card did inside its button.
    const flowInsideAnchor = container.querySelectorAll(
      'a div, a p, a h1, a h2, a h3, a h4, a h5, a h6, a section, a ul, a li'
    );
    expect(flowInsideAnchor).toHaveLength(0);
  });

  it('renders both actions inside ONE bar, not two detached cards', () => {
    const { container } = renderWithProviders(<QuickAccessCompact lng="fr" />);

    const links = Array.from(container.querySelectorAll('a'));
    expect(links).toHaveLength(2);
    // Same parent: that is what makes it a bar rather than a grid of cards.
    expect(links[0].parentElement).toBe(links[1].parentElement);
    // And that parent is the component root — no intermediate card wrapper.
    expect(links[0].parentElement).toBe(container.firstElementChild);
  });
});
