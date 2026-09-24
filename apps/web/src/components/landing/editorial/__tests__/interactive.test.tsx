/**
 * Behavioural + keyboard a11y coverage for the editorial interactive bricks:
 * the catalog disclosure (native button, aria-expanded, content stays in the
 * DOM while collapsed, deep-linkable through its anchor) and the tabs
 * (WAI-ARIA pattern, arrow-key roving).
 */

import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { CatalogDisclosure } from '../CatalogDisclosure';
import { Tabs } from '../Tabs';

/** Move the URL fragment the way a followed link does, and say so to listeners. */
function navigateToHash(hash: string): void {
  act(() => {
    window.history.replaceState(null, '', hash || window.location.pathname);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

describe('CatalogDisclosure', () => {
  afterEach(() => {
    window.history.replaceState(null, '', window.location.pathname);
  });

  it('is folded on arrival and unfolds on demand, content always in the DOM', async () => {
    const user = userEvent.setup();
    render(
      <CatalogDisclosure summary="Everything here" hint="8 items">
        <p>detailed card copy</p>
      </CatalogDisclosure>
    );

    const button = screen.getByRole('button', { name: /Everything here/ });
    // Owner arbitration 2026-09-24: the chapters read first, the catalog on demand.
    expect(button).toHaveAttribute('aria-expanded', 'false');
    const panel = document.getElementById(button.getAttribute('aria-controls') ?? '');
    // SEO contract: collapsed content is hidden, not removed — and untabbable.
    expect(screen.getByText('detailed card copy')).toBeInTheDocument();
    expect(panel?.firstElementChild).toHaveAttribute('inert');

    await user.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(panel?.firstElementChild).not.toHaveAttribute('inert');

    // Keyboard toggle (native button: Enter + Space).
    button.focus();
    await user.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await user.keyboard(' ');
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens when the page is reached through its anchor', () => {
    window.history.replaceState(null, '', '#c1-detail');
    render(
      <CatalogDisclosure summary="Everything here" anchor="c1-detail">
        <p>detailed card copy</p>
      </CatalogDisclosure>
    );

    expect(screen.getByRole('button', { name: /Everything here/ })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
  });

  it('opens when a link later moves the hash to it, and keeps the reader toggle otherwise', async () => {
    const user = userEvent.setup();
    render(
      <CatalogDisclosure summary="Everything here" anchor="c2-detail">
        <p>detailed card copy</p>
      </CatalogDisclosure>
    );
    const button = screen.getByRole('button', { name: /Everything here/ });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    navigateToHash('#c2-detail');
    expect(button).toHaveAttribute('aria-expanded', 'true');

    // Folded by the reader while the hash still names it: the reader wins.
    await user.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'false');

    // Unfolded by the reader, then the hash moves elsewhere: it stays open.
    await user.click(button);
    navigateToHash('#changelog');
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });
});

describe('Tabs', () => {
  const items = [
    { id: 'a', label: 'Alpha', content: <p>panel alpha</p> },
    { id: 'b', label: 'Beta', content: <p>panel beta</p> },
    { id: 'c', label: 'Gamma', content: <p>panel gamma</p> },
  ];

  it('exposes the WAI-ARIA tabs pattern and switches panels on click', async () => {
    const user = userEvent.setup();
    render(<Tabs items={items} label="Profiles" />);

    expect(screen.getByRole('tablist', { name: 'Profiles' })).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('panel alpha')).toBeVisible();
    expect(screen.getByText('panel beta')).not.toBeVisible();

    await user.click(tabs[1]);
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('panel beta')).toBeVisible();
    expect(screen.getByText('panel alpha')).not.toBeVisible();
  });

  it('selects the requested tab on first render, first tab when unknown', () => {
    const { unmount } = render(<Tabs items={items} label="Profiles" defaultTabId="c" />);
    expect(screen.getAllByRole('tab')[2]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('panel gamma')).toBeVisible();
    unmount();

    render(<Tabs items={items} label="Profiles" defaultTabId="does-not-exist" />);
    expect(screen.getAllByRole('tab')[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('supports arrow-key roving with wrap-around and Home/End', async () => {
    const user = userEvent.setup();
    render(<Tabs items={items} label="Profiles" />);
    const tabs = screen.getAllByRole('tab');

    tabs[0].focus();
    await user.keyboard('{ArrowRight}');
    expect(tabs[1]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    // wraps from first to last
    expect(tabs[2]).toHaveFocus();
    expect(tabs[2]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Home}');
    expect(tabs[0]).toHaveFocus();
    await user.keyboard('{End}');
    expect(tabs[2]).toHaveFocus();

    // Roving tabindex: only the active tab is tabbable.
    expect(tabs[2]).toHaveAttribute('tabindex', '0');
    expect(tabs[0]).toHaveAttribute('tabindex', '-1');
  });
});
