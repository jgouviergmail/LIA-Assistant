/**
 * SettingsSection — ONE layout: an open card.
 *
 * Since the master-detail shell (ADR-227) the settings page mounts exactly one
 * section at a time, opened. The collapsible/accordion mode it used to carry
 * had no production call site left — it survived only in tests, which is the
 * definition of dead code (root CLAUDE.md: "wire it or remove it").
 *
 * Two structural contracts stay pinned, because both were broken silently once
 * and neither shows up in a screenshot:
 *
 *  1. ONE heading per section — the accordion era rendered a second `<h3>`
 *     inside the trigger button, so every section appeared twice in a screen
 *     reader's heading list.
 *  2. The stable anchor `#settings-section-<value>` and its `tabIndex={-1}`:
 *     the pane polls the first to detect a section that renders nothing, and
 *     focuses the second when a search pick lands here.
 */

import { describe, it, expect } from 'vitest';
import { Star } from 'lucide-react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { SettingsSection } from '../SettingsSection';

describe('SettingsSection', () => {
  it('renders the title, description, icon and content always visible', () => {
    renderWithProviders(
      <SettingsSection value="s" title="My section" description="What it does" icon={Star}>
        <p>Body content</p>
      </SettingsSection>
    );
    expect(screen.getByRole('heading', { name: 'My section' })).toBeInTheDocument();
    expect(screen.getByText('What it does')).toBeVisible();
    expect(screen.getByText('Body content')).toBeVisible();
  });

  it('exposes exactly one heading', () => {
    renderWithProviders(
      <SettingsSection value="s" title="My section" description="What it does">
        <p>Body content</p>
      </SettingsSection>
    );
    expect(screen.getAllByRole('heading')).toHaveLength(1);
  });

  it('renders no disclosure control — the section is open, permanently', () => {
    renderWithProviders(
      <SettingsSection value="s" title="My section">
        <p>Body content</p>
      </SettingsSection>
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('needs no Accordion ancestor to render', () => {
    // The whole point of the removal: the component is standalone. Rendered
    // bare, the accordion branch used to throw ("must be used within
    // Accordion"), which is why 19 test files carried a wrapper.
    expect(() =>
      renderWithProviders(
        <SettingsSection value="s" title="Standalone">
          <p>Body content</p>
        </SettingsSection>
      )
    ).not.toThrow();
    expect(screen.getByText('Body content')).toBeVisible();
  });

  it('keeps the stable anchor id, which the pane polls for', () => {
    const { container } = renderWithProviders(
      <SettingsSection value="voice-mode" title="Voice">
        <p>content</p>
      </SettingsSection>
    );
    expect(container.querySelector('#settings-section-voice-mode')).not.toBeNull();
  });

  it('is programmatically focusable, so a search pick can land the reader on it', () => {
    const { container } = renderWithProviders(
      <SettingsSection value="theme" title="Theme">
        <p>content</p>
      </SettingsSection>
    );
    expect(container.querySelector<HTMLElement>('#settings-section-theme')).toHaveAttribute(
      'tabindex',
      '-1'
    );
  });
});
