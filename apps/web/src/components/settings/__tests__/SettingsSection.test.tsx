/**
 * SettingsSection — the static (non-collapsible) card layout and the collapsible
 * accordion layout.
 *
 * Two structural contracts are pinned here, because both were broken silently
 * and neither shows up in a screenshot:
 *
 *  1. ONE heading per section. Radix's `Accordion.Header` already renders an
 *     `<h3>` around the trigger; the component used to render a second `<h3>`
 *     INSIDE the button. Every one of the ~30 settings sections therefore
 *     appeared twice in a screen reader's heading list, and a heading nested in
 *     a `<button>` is invalid HTML (a button takes phrasing content only).
 *
 *  2. The chevron must be reachable by the rotation selector. The class read
 *     `[&[data-state=open]>div>svg.chevron]` while the chevron is a DIRECT
 *     child of the trigger — the selector could never match, so the chevron
 *     never turned when a section opened. A CSS rule cannot be observed in
 *     jsdom, but the DOM shape the selector depends on can.
 */

import { describe, it, expect } from 'vitest';
import { Star } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';
import { SettingsSection } from '../SettingsSection';

describe('SettingsSection — non-collapsible', () => {
  it('renders the title, description, icon and content always visible', () => {
    renderWithProviders(
      <SettingsSection
        value="s"
        title="My section"
        description="What it does"
        icon={Star}
        collapsible={false}
      >
        <p>Body content</p>
      </SettingsSection>
    );
    expect(screen.getByRole('heading', { name: 'My section' })).toBeInTheDocument();
    expect(screen.getByText('What it does')).toBeInTheDocument();
    expect(screen.getByText('Body content')).toBeInTheDocument();
  });

  it('exposes exactly one heading', () => {
    renderWithProviders(
      <SettingsSection value="s" title="My section" description="What it does" collapsible={false}>
        <p>Body content</p>
      </SettingsSection>
    );
    expect(screen.getAllByRole('heading')).toHaveLength(1);
  });
});

describe('SettingsSection — collapsible', () => {
  function renderCollapsible() {
    return renderWithProviders(
      <Accordion type="multiple">
        <SettingsSection
          value="s"
          title="Collapsible section"
          description="What it does"
          icon={Star}
        >
          <p>Hidden body</p>
        </SettingsSection>
      </Accordion>
    );
  }

  it('renders the title in an accordion trigger, collapsed by default', () => {
    renderCollapsible();
    // Title is always in the trigger; the body is not visible until expanded.
    expect(screen.getByText('Collapsible section')).toBeInTheDocument();
    expect(screen.queryByText('Hidden body')).not.toBeInTheDocument();
  });

  it('reveals the content once the trigger is activated', async () => {
    const { user } = renderCollapsible();
    await user.click(screen.getByRole('button', { name: /Collapsible section/ }));
    expect(screen.getByText('Hidden body')).toBeInTheDocument();
  });

  it('exposes exactly one heading — the section must not appear twice in the outline', () => {
    renderCollapsible();
    expect(screen.getAllByRole('heading')).toHaveLength(1);
  });

  it('never nests a heading inside the trigger button', () => {
    renderCollapsible();
    const trigger = screen.getByRole('button', { name: /Collapsible section/ });
    expect(trigger.querySelector('h1, h2, h3, h4, h5, h6')).toBeNull();
  });

  it('keeps the trigger accessible name: title AND description', () => {
    renderCollapsible();
    const trigger = screen.getByRole('button', { name: /Collapsible section/ });
    expect(trigger).toHaveAccessibleName(/Collapsible section/);
    expect(trigger).toHaveAccessibleName(/What it does/);
  });

  it('puts only phrasing content inside the trigger (valid HTML)', () => {
    const { container } = renderCollapsible();
    // A <button> accepts phrasing content only — div/p/heading inside one is
    // invalid markup, and that is what this component used to emit.
    expect(container.querySelectorAll('button div, button p, button h3')).toHaveLength(0);
  });

  it('exposes the trigger as a disclosure button carrying aria-expanded', () => {
    const { container } = renderCollapsible();
    // Relied upon by the settings page: when a search result is picked, focus
    // moves to `#settings-section-<value> button[aria-expanded]`. Radix sets the
    // attribute, so nothing in this repo would fail if it stopped — hence this
    // pin. A generic "first button" fallback exists, but it would silently land
    // on the wrong control the day a section grows one inside its header.
    const trigger = container.querySelector('[id^="settings-section-"] button[aria-expanded]');
    expect(trigger).not.toBeNull();
    expect(trigger).toHaveAccessibleName(/Collapsible section/);
  });

  it('keeps the chevron a DIRECT child of the trigger (rotation selector)', () => {
    renderCollapsible();
    const trigger = screen.getByRole('button', { name: /Collapsible section/ });
    // The selector that rotates it is `[data-state=open] > svg.chevron`.
    expect(trigger.querySelector(':scope > svg.chevron')).not.toBeNull();
  });
});
