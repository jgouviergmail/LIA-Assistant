/**
 * StarterChecklistCard (UXR Lot 6, A10) — flag-gated item visibility, the
 * never-render rule once dismissed/celebrated, live detection rendering,
 * dismissal persistence, and the two 100% paths (silent pre-completed vs
 * celebrated live transition).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { ChecklistState } from '../StarterChecklistCard';

const mutate = vi.fn(async () => ({}));
const auth = {
  user: { id: 'u1', voice_enabled: false, onboarding_checklist: null } as Record<
    string,
    unknown
  > | null,
};
const config = {
  features: {
    channels_enabled: true,
    heartbeat_enabled: true,
    rag_spaces_enabled: true,
  },
};
const probes = {
  connectors: [] as unknown[],
  personalityId: null as string | null,
  bindings: [] as unknown[],
  heartbeatEnabled: false,
  spaces: [] as unknown[],
  actions: [] as unknown[],
};

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: auth.user }) }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config }) }));
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: () => ({ data: { connectors: probes.connectors }, loading: false, error: null }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate }) }));
vi.mock('@/hooks/usePersonality', () => ({
  usePersonality: () => ({ currentPersonalityId: probes.personalityId }),
}));
vi.mock('@/hooks/useChannelBindings', () => ({
  useChannelBindings: () => ({ bindings: probes.bindings }),
}));
vi.mock('@/hooks/useHeartbeatSettings', () => ({
  useHeartbeatSettings: () => ({ settings: { heartbeat_enabled: probes.heartbeatEnabled } }),
}));
vi.mock('@/hooks/useSpaces', () => ({ useSpaces: () => ({ spaces: probes.spaces }) }));
vi.mock('@/hooks/useScheduledActions', () => ({
  useScheduledActions: () => ({ actions: probes.actions }),
}));

import {
  StarterChecklistCard,
  shouldRenderChecklist,
  visibleChecklistItems,
} from '../StarterChecklistCard';

beforeEach(() => {
  vi.clearAllMocks();
  auth.user = { id: 'u1', voice_enabled: false, onboarding_checklist: null };
  config.features = { channels_enabled: true, heartbeat_enabled: true, rag_spaces_enabled: true };
  Object.assign(probes, {
    connectors: [],
    personalityId: null,
    bindings: [],
    heartbeatEnabled: false,
    spaces: [],
    actions: [],
  });
});

describe('visibleChecklistItems — gate-keeper (ADR-061)', () => {
  it('offers all 7 items on a fully enabled instance', () => {
    expect(
      visibleChecklistItems({ channels: true, heartbeat: true, ragSpaces: true })
    ).toHaveLength(7);
  });

  it('never offers a disabled subsystem', () => {
    const items = visibleChecklistItems({ channels: false, heartbeat: false, ragSpaces: false });
    expect(items).toEqual(['connector', 'personality', 'voice', 'automation']);
  });
});

describe('shouldRenderChecklist — the never-again rule', () => {
  it.each<[ChecklistState | null, boolean]>([
    [null, true],
    [{}, true],
    [{ dismissed_at: '2026-07-23T00:00:00Z' }, false],
    [{ celebrated_at: '2026-07-23T00:00:00Z' }, false],
  ])('%j renders=%s', (state, expected) => {
    expect(shouldRenderChecklist(state)).toBe(expected);
  });
});

describe('StarterChecklistCard', () => {
  it('renders the 7 items with live detection states', () => {
    probes.personalityId = 'cynic';
    render(<StarterChecklistCard />);
    expect(screen.getByText('dashboard.checklist.title')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(7);
    // Done item is not a link anymore; undone items link to their journey.
    expect(
      screen.queryByRole('link', { name: 'dashboard.checklist.items.personality' })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'dashboard.checklist.items.connector' })
    ).toBeInTheDocument();
  });

  /**
   * W2: six of the seven items used to point at the bare settings page, which
   * meant landing at the top of ~30 collapsed accordions with nothing saying
   * where to look. Every item must now carry its own `?section=` token.
   */
  it('sends every undone item to its own settings section', () => {
    render(<StarterChecklistCard />);

    const expected: Record<string, string> = {
      connector: 'connectors',
      personality: 'personality',
      voice: 'voice-mode',
      telegram: 'channels',
      heartbeat: 'heartbeat',
      space: 'rag-spaces',
      automation: 'scheduled-actions',
    };

    for (const [item, token] of Object.entries(expected)) {
      const link = screen.getByRole('link', { name: `dashboard.checklist.items.${item}` });
      expect(link, `${item} must deep-link to its section`).toHaveAttribute(
        'href',
        `/fr/dashboard/settings?section=${token}`
      );
    }
  });

  it('never renders once dismissed server-side', () => {
    auth.user = { id: 'u1', onboarding_checklist: { dismissed_at: '2026-07-23T00:00:00Z' } };
    const { container } = render(<StarterChecklistCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it('persists the dismissal and disappears', async () => {
    render(<StarterChecklistCard />);
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.checklist.dismiss' }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/auth/me/onboarding-checklist', { dismissed: true })
    );
    expect(screen.queryByText('dashboard.checklist.title')).not.toBeInTheDocument();
  });

  it('silently persists celebration when 100% at first sight (no render)', async () => {
    Object.assign(probes, {
      connectors: [{}],
      personalityId: 'cynic',
      bindings: [{}],
      heartbeatEnabled: true,
      spaces: [{}],
      actions: [{}],
    });
    auth.user = { id: 'u1', voice_enabled: true, onboarding_checklist: null };
    render(<StarterChecklistCard />);
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/auth/me/onboarding-checklist', { celebrated: true })
    );
    expect(screen.queryByText('dashboard.checklist.celebration')).not.toBeInTheDocument();
  });
});

/** Mirrors the global setup mock, flipping only the reduced-motion query. */
function mockReducedMotion(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)' ? matches : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('StarterChecklistCard — celebration sparkle (UX P18)', () => {
  afterEach(() => mockReducedMotion(false));

  /** Renders incomplete, then flips every probe to done and rerenders. */
  function liveTransitionToComplete() {
    const view = render(<StarterChecklistCard />);
    Object.assign(probes, {
      connectors: [{}],
      personalityId: 'cynic',
      bindings: [{}],
      heartbeatEnabled: true,
      spaces: [{}],
      actions: [{}],
    });
    auth.user = { id: 'u1', voice_enabled: true, onboarding_checklist: null };
    view.rerender(<StarterChecklistCard />);
    return view;
  }

  it('bursts a small one-shot sparkle around the live celebration', () => {
    liveTransitionToComplete();
    expect(screen.getByText('dashboard.checklist.celebration')).toBeInTheDocument();
    const particles = document.querySelectorAll('.animate-particle-up');
    expect(particles).toHaveLength(6);
  });

  it('stays sparkle-free under prefers-reduced-motion', () => {
    mockReducedMotion(true);
    liveTransitionToComplete();
    expect(screen.getByText('dashboard.checklist.celebration')).toBeInTheDocument();
    expect(document.querySelector('.animate-particle-up')).toBeNull();
  });
});
