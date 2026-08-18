/**
 * SettingsSection — the pane mode of the master-detail shell.
 *
 * The 50 section components render `<SettingsSection>` and must not change for
 * the shell to switch from accordions to a master-detail pane. The switch is a
 * CONTEXT (`SettingsShellModeProvider`): under `mode="pane"` the section
 * renders its non-collapsible form — header always visible, children always
 * mounted, no disclosure button — while every call site outside the provider
 * keeps the accordion behaviour it always had.
 */

import { Palette } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

import { SettingsSection } from '../SettingsSection';
import { SettingsShellModeProvider } from '../settings-shell-context';

describe('SettingsSection — pane mode', () => {
  it('renders header and children with no disclosure button under the pane provider', () => {
    renderWithProviders(
      <SettingsShellModeProvider value="pane">
        <SettingsSection value="theme" title="Theme title" description="Theme desc" icon={Palette}>
          <p>the content</p>
        </SettingsSection>
      </SettingsShellModeProvider>
    );

    expect(screen.getByText('Theme title')).toBeVisible();
    expect(screen.getByText('Theme desc')).toBeVisible();
    expect(screen.getByText('the content')).toBeVisible();
    // No accordion trigger: the pane shows the section opened, permanently.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('keeps the stable anchor id, which deep-link revealing polls for', () => {
    const { container } = renderWithProviders(
      <SettingsShellModeProvider value="pane">
        <SettingsSection value="voice-mode" title="Voice">
          <p>content</p>
        </SettingsSection>
      </SettingsShellModeProvider>
    );
    expect(container.querySelector('#settings-section-voice-mode')).not.toBeNull();
  });

  it('is programmatically focusable, so a search pick can land the reader on it', () => {
    const { container } = renderWithProviders(
      <SettingsShellModeProvider value="pane">
        <SettingsSection value="theme" title="Theme">
          <p>content</p>
        </SettingsSection>
      </SettingsShellModeProvider>
    );
    const anchor = container.querySelector<HTMLElement>('#settings-section-theme');
    expect(anchor).toHaveAttribute('tabindex', '-1');
  });

  it('still renders as a collapsed accordion item outside the provider', () => {
    renderWithProviders(
      <Accordion type="multiple" value={[]}>
        <SettingsSection value="theme" title="Theme title">
          <p>the content</p>
        </SettingsSection>
      </Accordion>
    );
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('the content')).not.toBeInTheDocument();
  });
});
