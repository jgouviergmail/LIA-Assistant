/**
 * Mobile navigation through the logo (A2).
 *
 * Below `md` the header's `<nav>` is hidden and nothing replaced it: from the
 * chat, a phone user could reach the dashboard and NOTHING else. What must hold
 * now:
 *
 *  - every destination the desktop nav offers is reachable — a menu missing one
 *    would strand that page on phones, silently;
 *  - the current page is announced, not merely tinted (`aria-current`);
 *  - the trigger is a NAMED native button: it is the only interactive landmark
 *    in that corner, and an unnamed one is a dead end for a screen reader.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { DASHBOARD_DESTINATIONS, destinationPath, visibleDestinations } from '@/lib/dashboard-nav';

import { MobileNavMenu } from '../MobileNavMenu';

/** Mirrors the layout's own localized path builder. */
const buildHref = (route: string) => `/fr${route}`;
const translate = (key: string) => key;

function render(activeSegment = '') {
  return renderWithProviders(
    <MobileNavMenu
      buildHref={buildHref}
      translate={translate}
      isActiveRoute={segment => segment === activeSegment}
      triggerLabel="Menu"
    />
  );
}

describe('MobileNavMenu — the trigger', () => {
  it('is a named native button', () => {
    render();
    const trigger = screen.getByRole('button', { name: 'Menu' });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute('type', 'button');
  });

  it('shows nothing until it is opened', () => {
    render();
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
  });
});

describe('MobileNavMenu — the destinations', () => {
  it('offers every destination the desktop nav has', async () => {
    // A missing entry would strand that page on phones, and only there.
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'Menu' }));

    for (const { labelKey } of DASHBOARD_DESTINATIONS) {
      expect(await screen.findByRole('menuitem', { name: labelKey })).toBeInTheDocument();
    }
  });

  it('links each one to its localized route', async () => {
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'Menu' }));

    for (const { segment, labelKey } of DASHBOARD_DESTINATIONS) {
      const item = await screen.findByRole('menuitem', { name: labelKey });
      expect(item).toHaveAttribute('href', `/fr${destinationPath(segment)}`);
    }
  });

  it('keeps "go home" reachable, which the logo alone used to provide', async () => {
    // Turning the logo into a menu must not cost the gesture it replaced.
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'Menu' }));

    const home = await screen.findByRole('menuitem', { name: 'navigation.dashboard' });
    expect(home).toHaveAttribute('href', '/fr/dashboard');
  });

  it('announces the current page rather than only tinting it', async () => {
    const { user } = render('chat');
    await user.click(screen.getByRole('button', { name: 'Menu' }));

    expect(await screen.findByRole('menuitem', { name: 'navigation.chat' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(
      await screen.findByRole('menuitem', { name: 'navigation.settings' })
    ).not.toHaveAttribute('aria-current');
  });

  it('marks the root as current at the dashboard root', async () => {
    const { user } = render('');
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(await screen.findByRole('menuitem', { name: 'navigation.dashboard' })).toHaveAttribute(
      'aria-current',
      'page'
    );
  });

  it('opens from the keyboard', async () => {
    // The trigger replaces a link: it must stay reachable without a pointer.
    const { user } = render();
    const trigger = screen.getByRole('button', { name: 'Menu' });
    trigger.focus();
    expect(trigger).toHaveFocus();

    await user.keyboard('{Enter}');

    expect(await screen.findByRole('menuitem', { name: 'navigation.chat' })).toBeInTheDocument();
  });

  it('renders exactly one entry per destination', async () => {
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(await screen.findAllByRole('menuitem')).toHaveLength(DASHBOARD_DESTINATIONS.length);
  });
});

describe('DASHBOARD_DESTINATIONS — the contract', () => {
  it('has no duplicate segment', () => {
    const segments = DASHBOARD_DESTINATIONS.map(d => d.segment);
    expect(new Set(segments).size).toBe(segments.length);
  });

  it('builds the root without a trailing segment', () => {
    expect(destinationPath('')).toBe('/dashboard');
    expect(destinationPath('chat')).toBe('/dashboard/chat');
  });

  it('names every destination with a navigation key', () => {
    // A wrong namespace would render the raw key in the menu.
    for (const { labelKey } of DASHBOARD_DESTINATIONS) {
      expect(labelKey).toMatch(/^navigation\./);
    }
  });
});

describe('MobileNavMenu — instance-gated destinations (ADR-258)', () => {
  it('renders exactly the destinations the layout hands it', async () => {
    const { user } = renderWithProviders(
      <MobileNavMenu
        buildHref={buildHref}
        translate={translate}
        isActiveRoute={() => false}
        triggerLabel="Menu"
        destinations={visibleDestinations({ meetings_enabled: false })}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(screen.queryByRole('menuitem', { name: 'navigation.meetings' })).not.toBeInTheDocument();
    expect(await screen.findAllByRole('menuitem')).toHaveLength(DASHBOARD_DESTINATIONS.length - 1);
  });

  it('offers the meetings page where the instance has the feature on', async () => {
    const { user } = renderWithProviders(
      <MobileNavMenu
        buildHref={buildHref}
        translate={translate}
        isActiveRoute={() => false}
        triggerLabel="Menu"
        destinations={visibleDestinations({ meetings_enabled: true })}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(await screen.findByRole('menuitem', { name: 'navigation.meetings' })).toHaveAttribute(
      'href',
      '/fr/dashboard/meetings'
    );
  });
});

