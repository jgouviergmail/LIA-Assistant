/**
 * Behavioural + keyboard a11y coverage for the editorial interactive bricks:
 * the catalog disclosure (native button, aria-expanded, content stays in the
 * DOM while collapsed) and the tabs (WAI-ARIA pattern, arrow-key roving).
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { CatalogDisclosure } from '../CatalogDisclosure';
import { Tabs } from '../Tabs';

describe('CatalogDisclosure', () => {
  it('toggles with a native button and keeps content in the DOM while collapsed', async () => {
    const user = userEvent.setup();
    render(
      <CatalogDisclosure summary="Everything here" hint="8 items">
        <p>detailed card copy</p>
      </CatalogDisclosure>
    );

    const button = screen.getByRole('button', { name: /Everything here/ });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    // SEO contract: collapsed content is hidden, not removed.
    expect(screen.getByText('detailed card copy')).toBeInTheDocument();

    await user.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');

    // Keyboard toggle (native button: Enter + Space).
    button.focus();
    await user.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await user.keyboard(' ');
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
