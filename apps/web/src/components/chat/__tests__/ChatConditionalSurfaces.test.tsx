/**
 * ChatConditionalSurfaces — the arbiter's decision reaches the DOM (S1).
 *
 * The decision table itself is pinned in `lib/__tests__/chat-surfaces.test.ts`;
 * what matters here is the wiring: a surface that does not hold the slot must
 * be UNMOUNTED, not merely hidden, so it costs no vertical space — the whole
 * point of the arbitration (measured: 443 px of chrome on a 716 px shell).
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { visibleChatSurfaces, type ChatSurface } from '@/lib/chat-surfaces';
import { initialHitlCardState } from '@/types/hitl';

import {
  ChatConditionalSurfaces,
  type ChatConditionalSurfacesProps,
} from '../ChatConditionalSurfaces';

const SUGGESTIONS = ['Décale le rendez-vous', 'Envoie un récapitulatif'];

function props(over: Partial<ChatConditionalSurfacesProps> = {}): ChatConditionalSurfacesProps {
  return {
    surfaces: new Set<ChatSurface>(),
    followupSuggestions: SUGGESTIONS,
    onFollowupPick: vi.fn(),
    currentMessage: '',
    hitl: initialHitlCardState,
    onHitlAction: vi.fn(),
    connectorNotices: [],
    onDismissConnectorNotice: vi.fn(),
    ...over,
  };
}

describe('ChatConditionalSurfaces — follow-up chips', () => {
  it('mounts the chips when they hold the slot', () => {
    renderWithProviders(
      <ChatConditionalSurfaces {...props({ surfaces: new Set<ChatSurface>(['followups']) })} />
    );
    for (const suggestion of SUGGESTIONS) {
      expect(screen.getByRole('button', { name: suggestion })).toBeInTheDocument();
    }
  });

  it('does not mount them when they do not — suggestions alone are not enough', () => {
    // Same suggestions, empty slot set: nothing renders. This is what proves
    // the component obeys the arbiter rather than its own data.
    renderWithProviders(<ChatConditionalSurfaces {...props()} />);
    for (const suggestion of SUGGESTIONS) {
      expect(screen.queryByRole('button', { name: suggestion })).toBeNull();
    }
  });

  it('hands the exact chip text to the caller (A2 prefill contract)', async () => {
    const onFollowupPick = vi.fn();
    const { user } = renderWithProviders(
      <ChatConditionalSurfaces
        {...props({ surfaces: new Set<ChatSurface>(['followups']), onFollowupPick })}
      />
    );
    await user.click(screen.getByRole('button', { name: SUGGESTIONS[1] }));
    expect(onFollowupPick).toHaveBeenCalledWith(SUGGESTIONS[1]);
  });
});

describe('ChatConditionalSurfaces — always-mounted surfaces', () => {
  it('renders no HITL card when the state is `none` (the card owns that gate)', () => {
    const { container } = renderWithProviders(<ChatConditionalSurfaces {...props()} />);
    expect(container.querySelector('section')).toBeNull();
  });

  it('renders nothing at all when every surface is idle', () => {
    // No stray wrapper, no padding: an idle band must cost zero pixels.
    const { container } = renderWithProviders(<ChatConditionalSurfaces {...props()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('ChatConditionalSurfaces — arbitration end to end', () => {
  it('drops the chips when a pending approval takes priority', () => {
    // Wired exactly as the page does it: the arbiter decides, the component obeys.
    const surfaces = visibleChatSurfaces({
      usageBlocked: false,
      hitlAwaitingAction: true,
      hasConnectorNotices: false,
      wantsGeolocationPrompt: true,
      hasFollowups: true,
    });
    renderWithProviders(<ChatConditionalSurfaces {...props({ surfaces })} />);
    expect(screen.queryByRole('button', { name: SUGGESTIONS[0] })).toBeNull();
  });

  it('shows the chips once nothing blocks any more', () => {
    const surfaces = visibleChatSurfaces({
      usageBlocked: false,
      hitlAwaitingAction: false,
      hasConnectorNotices: false,
      wantsGeolocationPrompt: false,
      hasFollowups: true,
    });
    renderWithProviders(<ChatConditionalSurfaces {...props({ surfaces })} />);
    expect(screen.getByRole('button', { name: SUGGESTIONS[0] })).toBeInTheDocument();
  });
});
