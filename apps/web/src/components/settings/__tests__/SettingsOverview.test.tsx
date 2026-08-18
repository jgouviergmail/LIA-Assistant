/**
 * SettingsOverview — the desktop landing pane of the master-detail shell.
 *
 * Cards, not rows: each visible section as a clickable card carrying its icon,
 * title and description (the same i18n keys the section header renders), under
 * real `SettingsGroupLabel` h2 headings — the overview owns the page outline,
 * the rail deliberately does not. Clicking a card opens the section, exactly
 * like the rail.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
import type { SettingsSearchAvailability } from '@/lib/settings-search';

const { useCapabilities, useMediaQuery } = vi.hoisted(() => ({
  useCapabilities: vi.fn(),
  useMediaQuery: vi.fn(),
}));
vi.mock('@/hooks/useCapabilities', () => ({ useCapabilities }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery }));

/** Whether the viewport is wide enough for the hub to be on screen at all. */
let matchesWide = true;

import { SettingsOverview } from '../SettingsOverview';
import type { CapabilityMap } from '@/hooks/useCapabilities';

const AVAILABLE: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

type CapabilitiesHook = ReturnType<typeof import('@/hooks/useCapabilities').useCapabilities>;

function capabilities(over: Partial<CapabilitiesHook> = {}): CapabilitiesHook {
  const map: CapabilityMap = { nodes: [], live: 0, total: 0 };
  return {
    nodes: map.nodes,
    live: 0,
    total: 0,
    firstLoad: false,
    loading: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function renderOverview({
  availability = AVAILABLE,
  children = undefined as React.ReactNode,
  hook = capabilities(),
} = {}) {
  useCapabilities.mockReturnValue(hook);
  useMediaQuery.mockReturnValue(matchesWide);
  const onSelect = vi.fn();
  const model = buildSettingsShellModel(availability);
  const view = renderWithProviders(
    <SettingsOverview lng="en" model={model} onSelect={onSelect}>
      {children}
    </SettingsOverview>
  );
  return { ...view, onSelect };
}

beforeEach(() => {
  matchesWide = true;
  vi.clearAllMocks();
});

describe('SettingsOverview', () => {
  it('renders every visible section as a card with its title and description', () => {
    renderOverview();
    const themeCard = screen.getByRole('button', { name: /settings\.theme\.title/ });
    expect(themeCard).toBeInTheDocument();
    expect(themeCard).toHaveTextContent('settings.theme.description');
  });

  it('structures the page with real group headings', () => {
    renderOverview();
    expect(
      screen.getByRole('heading', { level: 2, name: /settings\.groups\.personalization/ })
    ).toBeInTheDocument();
  });

  it('shows administration cards to a superuser only', () => {
    renderOverview();
    expect(
      screen.queryByRole('button', { name: /settings\.admin\.users\.title/ })
    ).not.toBeInTheDocument();

    renderOverview({ availability: { ...AVAILABLE, isSuperuser: true } });
    expect(
      screen.getByRole('button', { name: /settings\.admin\.users\.title/ })
    ).toBeInTheDocument();
  });

  it('opens the picked section', async () => {
    const { user, onSelect } = renderOverview();
    await user.click(screen.getByRole('button', { name: /settings\.theme\.title/ }));
    expect(onSelect).toHaveBeenCalledWith('theme');
  });

  it('hosts a top slot — the portrait shortcut lives here', () => {
    renderOverview({ children: <p>portrait slot</p> });
    expect(screen.getByText('portrait slot')).toBeInTheDocument();
  });
});

describe('SettingsOverview — what each section currently holds', () => {
  const memoriesCard = () => screen.getByRole('button', { name: /memories\.settings\.title/ });

  it('quotes the exact count a live capability reports', () => {
    renderOverview({
      hook: capabilities({
        nodes: [{ key: 'memory', active: true, detail: 12 }],
        live: 1,
        total: 1,
      }),
    });

    // The SAME words the capability list uses (`activeLabel`): two surfaces
    // describing one capability must never phrase it differently.
    expect(memoriesCard()).toHaveTextContent('capabilities.state_active');
  });

  it('says "to set up" for a capability that exists but holds nothing', () => {
    renderOverview({
      hook: capabilities({ nodes: [{ key: 'memory', active: false, detail: 0 }], total: 1 }),
    });

    expect(memoriesCard()).toHaveTextContent('capabilities.state_dormant');
  });

  it('never invents a tally for a capability that has none', () => {
    // ADR-185: a count shown to the user is exact, or it does not exist.
    renderOverview({
      hook: capabilities({
        nodes: [{ key: 'personality', active: true, detail: null }],
        live: 1,
        total: 1,
      }),
    });

    const card = screen.getByRole('button', { name: /personality\.settings\.title/ });
    expect(card).toHaveTextContent('capabilities.state_active_plain');
  });

  it('stays silent about a section the payload says nothing about', () => {
    renderOverview({ hook: capabilities({ nodes: [{ key: 'memory', active: true, detail: 3 }] }) });

    const themeCard = screen.getByRole('button', { name: /settings\.theme\.title/ });
    expect(themeCard).not.toHaveTextContent('capabilities.state');
  });

  it('claims nothing at all while the answer is still in flight', () => {
    // A card that reads "to set up" during the first load would accuse an
    // account of being empty before anything was counted.
    renderOverview({ hook: capabilities({ firstLoad: true, loading: true }) });

    expect(memoriesCard()).not.toHaveTextContent('capabilities.state');
  });

  it('claims nothing when the read failed', () => {
    renderOverview({ hook: capabilities({ error: new Error('boom') }) });

    expect(memoriesCard()).not.toHaveTextContent('capabilities.state');
  });

  it('does not read the aggregate at all where the hub is not shown', () => {
    // Below `lg` this pane is CSS-hidden and the rail is the landing: fetching
    // there would be a request for a screen nobody can see — the opposite of
    // the rule the shell was built on.
    matchesWide = false;
    renderOverview();

    expect(useCapabilities).toHaveBeenCalledWith({ enabled: false });
  });

  it('reads it once the viewport is wide enough to show it', () => {
    matchesWide = true;
    renderOverview();

    expect(useCapabilities).toHaveBeenCalledWith({ enabled: true });
  });

  it('keeps the status line out of the card accessible name', () => {
    // The name is the destination ("Memory"); the tally is context that would
    // otherwise change what a screen-reader user hears the button is called.
    renderOverview({
      hook: capabilities({ nodes: [{ key: 'memory', active: true, detail: 12 }], live: 1 }),
    });

    // Shown, but not part of what the control is called.
    expect(within(memoriesCard()).getByText(/capabilities\.state_active/)).toBeVisible();
    expect(memoriesCard()).not.toHaveAccessibleName(/capabilities\.state_active/);
    expect(memoriesCard()).toHaveAccessibleName(/memories\.settings\.title/);
  });
});
