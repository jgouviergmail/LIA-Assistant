/**
 * SettingsPane — the territory half of the master-detail shell.
 *
 * Mounts ONE section, resolved through the registry, under the pane shell
 * mode. A section can legitimately render nothing (gated on capability, flag
 * or data): the pane then says so honestly — an inline empty state after the
 * same deadline the accordion page used for its toast — and keeps looking, so
 * a section whose request answers late replaces the message instead of
 * coexisting with it.
 *
 * Deterministic fixtures, no mocks of the boundary under test:
 * `chat-shortcuts` renders its shell immediately; `haptics` returns null in
 * jsdom (no `navigator.vibrate`), which is exactly the gated case.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { SettingsSearchAvailability } from '@/lib/settings-search';

import { SettingsPane, SECTION_SETTLE_DEADLINE_MS } from '../SettingsPane';

// The chat-shortcuts fixture section would fetch into the void under fake
// timers and pollute stderr; its own tests cover the hook. Shape mirrors
// `UseChatShortcutsReturn`.
vi.mock('@/hooks/useChatShortcuts', () => ({
  useChatShortcuts: () => ({
    shortcuts: [],
    maxCount: 4,
    loading: false,
    error: false,
    save: async () => true,
    saving: false,
  }),
}));

// Sections consult the signed-in user; auth is not the boundary under test.
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'u@example.test', is_superuser: false },
    refreshUser: async () => {},
  }),
}));

const AVAILABLE: SettingsSearchAvailability = {
  isSuperuser: false,
  openLoopsEnabled: true,
  habitsEnabled: true,
  peersEnabled: true,
  debugUserAccess: true,
};

/** Advance the fake clock inside `act`: the poll sets React state. */
function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe('SettingsPane', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('mounts the selected section, open, with its anchor id', () => {
    const { container } = renderWithProviders(
      <SettingsPane lng="en" availability={AVAILABLE} token="chat-shortcuts" onBack={() => {}} />
    );
    advance(500);
    expect(container.querySelector('#settings-section-chat-shortcuts')).not.toBeNull();
    expect(screen.getByText('settings.chat_shortcuts.title')).toBeInTheDocument();
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();
  });

  it('offers a way back below the desktop breakpoint', () => {
    renderWithProviders(<SettingsPane lng="en" availability={AVAILABLE} token="chat-shortcuts" onBack={() => {}} />);
    expect(screen.getByRole('button', { name: /settings\.shell\.back/ })).toBeInTheDocument();
  });

  it('says so honestly when the section renders nothing, after the settling deadline', () => {
    renderWithProviders(<SettingsPane lng="en" availability={AVAILABLE} token="haptics" onBack={() => {}} />);
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument();

    advance(SECTION_SETTLE_DEADLINE_MS + 500);
    const empty = screen.getByTestId('empty-state');
    expect(empty).toHaveTextContent('settings.search.unavailable');
  });

  it('routes the empty-state action back to the overview', () => {
    const onBack = vi.fn();
    renderWithProviders(<SettingsPane lng="en" availability={AVAILABLE} token="haptics" onBack={onBack} />);
    advance(SECTION_SETTLE_DEADLINE_MS + 500);

    fireEvent.click(screen.getByRole('button', { name: /settings\.shell\.browse_all/ }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('moves focus onto the settled section when asked — the search-pick contract', () => {
    const { container } = renderWithProviders(
      <SettingsPane lng="en" availability={AVAILABLE} token="chat-shortcuts" onBack={() => {}} focusRequest={1} />
    );
    advance(500);
    const anchor = container.querySelector<HTMLElement>('#settings-section-chat-shortcuts');
    expect(document.activeElement).toBe(anchor);
  });

  it('does not steal focus for a plain selection or deep link', () => {
    renderWithProviders(<SettingsPane lng="en" availability={AVAILABLE} token="chat-shortcuts" onBack={() => {}} />);
    advance(500);
    expect(document.activeElement).toBe(document.body);
  });

  it('honours one focus request ONCE — the next rail pick must not steal focus', () => {
    // The counter stays at its value after a search pick; a later selection
    // re-runs the settling effect with the same number, and focusing again
    // would yank the caret off the rail button the reader just clicked.
    const { container, rerender } = renderWithProviders(
      <SettingsPane
        lng="en"
        availability={AVAILABLE}
        token="chat-shortcuts"
        onBack={() => {}}
        focusRequest={1}
      />
    );
    advance(500);
    expect(document.activeElement?.id).toBe('settings-section-chat-shortcuts');

    rerender(
      <SettingsPane
        lng="en"
        availability={AVAILABLE}
        token="voice-mode"
        onBack={() => {}}
        focusRequest={1}
      />
    );
    advance(500);
    expect(container.querySelector('#settings-section-voice-mode')).not.toBeNull();
    expect(document.activeElement?.id).not.toBe('settings-section-voice-mode');
  });

  it('never mounts a section the availability gates rule out — it reports absence instead', () => {
    // A non-superuser deep-linking to an admin token: the section must not
    // mount (its queries would fail loudly), and the reader gets the same
    // honest absence message as any gated section.
    const { container } = renderWithProviders(
      <SettingsPane lng="en" availability={AVAILABLE} token="admin-users" onBack={() => {}} />
    );
    expect(container.querySelector('#settings-section-admin-users')).toBeNull();
    advance(SECTION_SETTLE_DEADLINE_MS + 500);
    expect(screen.getByTestId('empty-state')).toHaveTextContent('settings.search.unavailable');
  });
});
