/**
 * CustomizeBriefingButton — the "customize" companion of RefreshAllButton in
 * the briefing section header (UX P10). The grid has been configurable since
 * UXR Lot 5 (B4), but the capability lived buried in the settings; this link
 * surfaces it exactly where it becomes relevant, deep-linking straight to the
 * `briefing-grid` section.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { settingsSectionHref } from '@/lib/settings-sections';

import { CustomizeBriefingButton } from '../CustomizeBriefingButton';

vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: React.ComponentProps<'a'> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe('CustomizeBriefingButton', () => {
  it('deep-links to the briefing-grid settings section for the active locale', () => {
    renderWithProviders(<CustomizeBriefingButton lng="fr" />);
    const link = screen.getByRole('link', { name: 'dashboard.briefing.customize' });
    expect(link).toHaveAttribute('href', settingsSectionHref('fr', 'briefing-grid'));
  });

  it('keeps a visible desktop label alongside the icon', () => {
    renderWithProviders(<CustomizeBriefingButton lng="en" />);
    const link = screen.getByRole('link', { name: 'dashboard.briefing.customize' });
    expect(link.textContent).toContain('dashboard.briefing.customize');
  });
});
