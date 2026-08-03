/**
 * The sub-section disclosure of the settings panel.
 *
 * The proactivity panel stacks a frequency form, eleven source switches and a
 * ten-row history. Shown at once that is a wall; the reader came to change one
 * thing. Each block therefore folds, and folds CLOSED — the panel is an index
 * you open, not a page you scroll past.
 *
 * Two properties beyond the visual: the platform owns the semantics (a real
 * `<details>`, so keyboard and announcement come for free), and a closed block
 * renders nothing — which is what keeps a collapsed history from fetching a
 * page nobody is looking at.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { SettingsDisclosure } from '../SettingsDisclosure';
import { Bell } from 'lucide-react';

describe('SettingsDisclosure', () => {
  it('is closed on arrival and shows nothing of its content', () => {
    renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    expect(screen.getByText('Historique')).toBeInTheDocument();
    // Not merely hidden: absent. A `<details>` keeps its content in the DOM,
    // so a hook inside it would still run — and still fetch.
    expect(screen.queryByText('contenu')).not.toBeInTheDocument();
  });

  it('reveals its content when opened', async () => {
    const { user } = renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    await user.click(screen.getByText('Historique'));

    expect(await screen.findByText('contenu')).toBeInTheDocument();
  });

  it('tells the caller when it opens, so a fetch can wait for it', async () => {
    const onOpenChange = vi.fn();
    const { user } = renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique" onOpenChange={onOpenChange}>
        <p>contenu</p>
      </SettingsDisclosure>
    );

    await user.click(screen.getByText('Historique'));

    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it('carries the platform disclosure semantics rather than a div with a handler', () => {
    const { container } = renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    const details = container.querySelector('details');
    expect(details).toBeInTheDocument();
    expect(details?.querySelector('summary')).toHaveTextContent('Historique');
  });

  it('shows a badge next to the title when one is given', () => {
    renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique" badge="57">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    // Inside the summary: folded, the count is the only thing left to choose
    // from, exactly as the 360° sections do it.
    expect(screen.getByText('57')).toBeInTheDocument();
  });

  it('can be asked to start open', () => {
    renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique" defaultOpen>
        <p>contenu</p>
      </SettingsDisclosure>
    );

    expect(screen.getByText('contenu')).toBeInTheDocument();
  });
});

describe('a parent re-render must not shut it under the reader', () => {
  // `open` is passed to a real `<details>`. Toggling a source switch above
  // makes the whole settings panel re-render, and a controlled `open` that
  // snapped back to `defaultOpen` would close the block the reader is using —
  // the same "unmounts under the user" defect class the peers panel had.
  it('stays open across a re-render of its parent', async () => {
    const { user, rerender } = renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    await user.click(screen.getByText('Historique'));
    expect(await screen.findByText('contenu')).toBeInTheDocument();

    // Same props, new render pass — exactly what a settings mutation causes.
    rerender(
      <SettingsDisclosure icon={Bell} title="Historique">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    expect(screen.getByText('contenu')).toBeInTheDocument();
  });

  it('stays open when a sibling prop changes', async () => {
    const { user, rerender } = renderWithProviders(
      <SettingsDisclosure icon={Bell} title="Historique" badge="1">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    await user.click(screen.getByText('Historique'));
    expect(await screen.findByText('contenu')).toBeInTheDocument();

    // The badge is the refused-source count: it changes the moment the reader
    // flips a switch, which is precisely when the block must not close.
    rerender(
      <SettingsDisclosure icon={Bell} title="Historique" badge="2">
        <p>contenu</p>
      </SettingsDisclosure>
    );

    expect(screen.getByText('contenu')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});
