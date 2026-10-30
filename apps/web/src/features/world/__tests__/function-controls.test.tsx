import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@/lib/auth';
import { makeUser } from '@/__tests__/factories';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { createRef, useEffect, useState } from 'react';
import { WorldFunctionControls, type WorldFunctionHandle } from '../WorldFunctionControls';
import { WorldAccountGuard } from '../WorldAccountGuard';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { DashboardNavigate } from '@/components/dashboard/DashboardNavigation';

vi.mock('@/components/dashboard/DashboardWorkspace', () => ({
  DashboardWorkspace: ({ onNavigate }: { onNavigate?: DashboardNavigate }) => {
    const [draft, setDraft] = useState('');
    return (
      <>
        <input
          aria-label="Retained dashboard choice"
          value={draft}
          onChange={event => setDraft(event.target.value)}
        />
        <button onClick={() => onNavigate?.({ kind: 'draft', draft: 'Hello Alice' })}>
          Open local draft
        </button>
      </>
    );
  },
}));
const chat = vi.hoisted(() => ({
  props: [] as Record<string, unknown>[],
  mounted: vi.fn(),
  cleaned: vi.fn(),
}));
vi.mock('@/components/chat/ChatWorkspace', () => ({
  ChatWorkspace: (props: { embedded?: boolean; openingDraft?: string }) => {
    chat.props.push({ ...props });
    // Stands in for the streaming chat: its effect owns the answer's transport.
    useEffect(() => {
      chat.mounted();
      return chat.cleaned;
    }, []);
    return <input aria-label="Native chat draft" defaultValue={props.openingDraft} />;
  },
}));

vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get: vi.fn(), post: vi.fn() },
}));

const auth = vi.hoisted(() => ({ user: null as User | null }));
const features = vi.hoisted(() => ({ radioEnabled: false }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => auth }));
vi.mock('@/hooks/useSettingsAvailability', () => ({
  useSettingsAvailability: () => ({ isSuperuser: false, radioEnabled: features.radioEnabled }),
}));
vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: string) => ({
    t: (key: string) => {
      let value: unknown = lng === 'fr' ? fr : en;
      for (const segment of key.split('.'))
        value =
          value && typeof value === 'object' && segment in value
            ? Reflect.get(value, segment)
            : undefined;
      return typeof value === 'string' ? value : key;
    },
  }),
}));

beforeEach(() => {
  features.radioEnabled = false;
  auth.user = makeUser({ id: 'owner', is_active: true });
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.post).mockReset();
  chat.props = [];
  chat.mounted.mockClear();
  chat.cleaned.mockClear();
});
/** The dashboard's act (spec 2026-10-21 §5.8): every card hidden, nothing pending. */
const DASHBOARD_INITIAL = '/briefing/cards/initial';
const HIDDEN_CARD = {
  status: 'hidden',
  data: null,
  generated_at: '2026-10-28T08:00:00Z',
  error_code: null,
  error_message: null,
  from_cache: false,
  stale_generated_at: null,
  last_attempt_at: null,
};
const DASHBOARD_ACT = {
  cards: Object.fromEntries(
    [
      'weather',
      'agenda',
      'mails',
      'birthdays',
      'reminders',
      'health',
      'for_you',
      'tasks',
      'documents',
      'workboard',
    ].map(name => [name, HIDDEN_CARD])
  ),
  windows: {
    birthdays_horizon_days: 7,
    health_window_days: 14,
    agenda_lookahead_hours: 24,
    tasks_horizon_days: 7,
    weather_forecast_days: 5,
  },
  pending: [],
  act: 'act-1',
  act_expires_at: '2026-10-28T08:10:00Z',
  section_concurrency: 4,
};
/** The initial read serves the act; the text is a POST of its own, counted below. */
function serveDashboardAct(): void {
  vi.mocked(apiClient.get).mockImplementation(async (endpoint: string) =>
    endpoint === DASHBOARD_INITIAL ? DASHBOARD_ACT : undefined
  );
  vi.mocked(apiClient.post).mockImplementation(async (endpoint: string) =>
    endpoint === '/briefing/text'
      ? {
          greeting: { text: 'Hello', generated_at: '2026-10-28T08:00:00Z', usage: null },
          synthesis: null,
          reused: false,
          state: 'ready',
        }
      : undefined
  );
}
const textPurchases = () =>
  vi.mocked(apiClient.post).mock.calls.filter(([endpoint]) => endpoint === '/briefing/text').length;

describe('private native function controls', () => {
  it.each(['disabled', 'body'])(
    'returns to the scene when the retained opener is %s while the activity closes',
    async mode => {
      const ref = createRef<WorldFunctionHandle>();
      const canvas = document.createElement('canvas');
      canvas.className = 'world-canvas';
      canvas.tabIndex = 0;
      const opener = document.createElement('button');
      document.body.append(canvas, opener);
      try {
        render(
          <WorldFunctionControls
            lng="en"
            ownerId="owner"
            enabled
            zone="arrival"
            onOpen={vi.fn()}
            functionRef={ref}
          />
        );
        opener.focus();
        if (mode === 'body') opener.blur();
        act(() => {
          expect(ref.current?.openDestination({ kind: 'draft', draft: 'Local only' })).toBe(true);
        });
        const input = await screen.findByRole('textbox', { name: 'Native chat draft' });
        if (mode === 'disabled') opener.disabled = true;
        fireEvent.keyDown(input, { key: 'Escape', code: 'Escape' });
        await waitFor(() => expect(canvas).toHaveFocus());
      } finally {
        opener.remove();
        canvas.remove();
      }
    }
  );
  it('keeps the current acting state readable inside the conversation panel', async () => {
    const ref = createRef<WorldFunctionHandle>();
    render(
      <WorldFunctionControls
        lng="en"
        ownerId="owner"
        enabled
        zone="arrival"
        onOpen={vi.fn()}
        functionRef={ref}
        actingState="waiting"
      />
    );
    act(() => {
      ref.current?.openDestination({ kind: 'draft', draft: 'Local only' });
    });
    expect(await screen.findByRole('status')).toHaveTextContent(en.world.acting.waiting);
  });
  it('returns to the scene when the phone action that opened a native panel has unmounted', async () => {
    const ref = createRef<WorldFunctionHandle>();
    const canvas = document.createElement('canvas');
    canvas.className = 'world-canvas';
    canvas.tabIndex = 0;
    const phoneAction = document.createElement('button');
    document.body.append(canvas, phoneAction);
    try {
      render(
        <WorldFunctionControls
          lng="en"
          ownerId="owner"
          enabled
          zone="arrival"
          onOpen={vi.fn()}
          functionRef={ref}
        />
      );
      phoneAction.focus();
      act(() => {
        expect(ref.current?.openDestination({ kind: 'draft', draft: 'Local only' })).toBe(true);
      });
      phoneAction.remove();
      const input = await screen.findByRole('textbox', { name: 'Native chat draft' });
      fireEvent.keyDown(input, { key: 'Escape', code: 'Escape' });
      await waitFor(() => expect(canvas).toHaveFocus());
    } finally {
      canvas.remove();
      phoneAction.remove();
    }
  });
  it('retains the accepted dashboard through the non-modal chat and native back navigation', async () => {
    const ref = createRef<WorldFunctionHandle>();
    render(
      <WorldFunctionControls
        lng="en"
        ownerId="owner"
        enabled
        zone="arrival"
        onOpen={vi.fn()}
        functionRef={ref}
        dashboardSeatKey="confirmed-seat"
      />
    );
    act(() => {
      ref.current?.openScene({ kind: 'workspace', id: 'dashboard' });
    });
    const choice = await screen.findByRole('textbox', { name: 'Retained dashboard choice' });
    fireEvent.change(choice, { target: { value: 'Preserved through chat' } });
    fireEvent.click(screen.getByRole('button', { name: 'Open local draft' }));
    // The dashboard hands the chat an unsent draft: prefilled, never sent or streamed.
    expect(await screen.findByRole('textbox', { name: 'Native chat draft' })).toHaveValue(
      'Hello Alice'
    );
    expect(chat.props.at(-1)).toEqual({ embedded: true, openingDraft: 'Hello Alice' });
    expect(apiClient.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: en.common.back }));
    expect(await screen.findByRole('textbox', { name: 'Retained dashboard choice' })).toHaveValue(
      'Preserved through chat'
    );
  });
  it('retains an accepted dashboard across closing, another activity and reopening', async () => {
    const ref = createRef<WorldFunctionHandle>();
    render(
      <WorldFunctionControls
        lng="en"
        ownerId="owner"
        enabled
        zone="arrival"
        onOpen={vi.fn()}
        functionRef={ref}
        dashboardSeatKey="confirmed-seat"
      />
    );
    act(() => {
      expect(ref.current?.openScene({ kind: 'workspace', id: 'dashboard' })).toBe(true);
    });
    const choice = await screen.findByRole('textbox', { name: 'Retained dashboard choice' });
    fireEvent.change(choice, { target: { value: 'Preserved owner choice' } });
    fireEvent.keyDown(choice, { key: 'Escape', code: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(document.body.style.pointerEvents).not.toBe('none');
    fireEvent.click(screen.getByRole('button', { name: 'LIA settings' }));
    await screen.findByRole('searchbox');
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
    act(() => {
      ref.current?.openScene({ kind: 'workspace', id: 'dashboard' });
    });
    expect(await screen.findByRole('textbox', { name: 'Retained dashboard choice' })).toHaveValue(
      'Preserved owner choice'
    );
  });
  it('disposes the dashboard when standing and starts a fresh workspace for a later seating', async () => {
    const ref = createRef<WorldFunctionHandle>();
    const props = {
      lng: 'en' as const,
      ownerId: 'owner',
      enabled: true,
      zone: 'arrival' as const,
      onOpen: vi.fn(),
      functionRef: ref,
    };
    const view = render(<WorldFunctionControls {...props} dashboardSeatKey="confirmed-seat" />);
    act(() => {
      ref.current?.openScene({ kind: 'workspace', id: 'dashboard' });
    });
    const choice = await screen.findByRole('textbox', { name: 'Retained dashboard choice' });
    fireEvent.change(choice, { target: { value: 'Old seating' } });
    view.rerender(<WorldFunctionControls {...props} dashboardSeatKey={null} />);
    await waitFor(() =>
      expect(
        screen.queryByRole('textbox', { name: 'Retained dashboard choice', hidden: true })
      ).not.toBeInTheDocument()
    );
    expect(ref.current?.canOpen({ kind: 'workspace', id: 'dashboard' })).toBe(false);
    view.rerender(<WorldFunctionControls {...props} dashboardSeatKey="confirmed-seat" />);
    act(() => {
      ref.current?.openScene({ kind: 'workspace', id: 'dashboard' });
    });
    expect(await screen.findByRole('textbox', { name: 'Retained dashboard choice' })).toHaveValue(
      ''
    );
  });
  it.each([
    ['en', 'LIA functions', 'Talk to LIA'],
    ['fr', 'Fonctions LIA', 'Parler à LIA'],
  ] as const)(
    'names actions in %s and forgets the open activity when authority is lost',
    async (lng, label, talk) => {
      const onOpen = vi.fn();
      const props = { lng, ownerId: 'owner', enabled: true, zone: 'arrival' as const, onOpen };
      const view = render(<WorldFunctionControls {...props} />);
      expect(screen.getByRole('button', { name: talk })).toBeEnabled();
      fireEvent.pointerDown(screen.getByRole('button', { name: label }), {
        button: 0,
        ctrlKey: false,
      });
      fireEvent.click(await screen.findByRole('menuitem', { name: label }));
      expect(screen.getByRole('dialog')).toBeVisible();
      expect(onOpen).toHaveBeenLastCalledWith(true, false);
      await act(async () => {
        view.rerender(<WorldFunctionControls {...props} enabled={false} />);
      });
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      view.rerender(<WorldFunctionControls {...props} />);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(onOpen).toHaveBeenLastCalledWith(false, false);
      await act(async () => {
        // Drain the remount read after checking synchronous closed-state behavior.
      });
    }
  );
  it('keeps every native operation unavailable when the world owner differs from the authenticated account', async () => {
    render(
      <WorldFunctionControls lng="en" ownerId="someone-else" enabled zone="home" onOpen={vi.fn()} />
    );
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await act(async () => {
      // Drain configuration only after checking immediate owner isolation.
    });
  });

  it('restores the private catalogue edit after a same-account verification', async () => {
    // Children read before their guard: answer the identity by its endpoint.
    vi.mocked(apiClient.get).mockImplementation(async (endpoint: string) =>
      endpoint === '/auth/me' ? { id: 'owner', is_active: true } : undefined
    );
    render(
      <WorldAccountGuard ownerId="owner" lng="en">
        <WorldFunctionControls lng="en" ownerId="owner" enabled zone="arrival" onOpen={vi.fn()} />
      </WorldAccountGuard>
    );
    const action = screen.getByRole('button', { name: 'LIA functions', hidden: true });
    await waitFor(() => expect(action).toBeEnabled());
    fireEvent.pointerDown(action, { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'LIA functions' }));
    const query = screen.getByRole('searchbox', { name: en.world.functions.search });
    fireEvent.change(query, { target: { value: 'Remember this query' } });
    const next = Promise.withResolvers<unknown>();
    vi.mocked(apiClient.get).mockImplementationOnce(() => next.promise);
    fireEvent(window, new Event('focus'));
    // A revalidation of the confirmed owner runs in the background.
    expect(query).toBeVisible();
    await act(async () => next.resolve({ id: 'owner', is_active: true }));
    expect(await screen.findByRole('searchbox', { name: en.world.functions.search })).toHaveValue(
      'Remember this query'
    );
  });
  it('keeps a local catalogue query across a recoverable transport suspension', async () => {
    const props = {
      lng: 'en' as const,
      ownerId: 'owner',
      enabled: true,
      zone: 'arrival' as const,
      onOpen: vi.fn(),
    };
    const view = render(<WorldFunctionControls {...props} />);
    fireEvent.pointerDown(screen.getByRole('button', { name: 'LIA functions' }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'LIA functions' }));
    const query = screen.getByRole('searchbox', { name: en.world.functions.search });
    fireEvent.change(query, { target: { value: 'Retained on reconnect' } });
    view.rerender(<WorldFunctionControls {...props} suspended />);
    // A reconnect keeps the panel mounted, readable and busy; the session dialog says why.
    expect(query).toBeVisible();
    expect(query).toHaveValue('Retained on reconnect');
    expect(query.closest('[aria-busy]')).toHaveAttribute('aria-busy', 'true');
    // New actions wait for the World; the open modal keeps the toolbar out of the tree.
    expect(screen.getByRole('button', { name: 'LIA functions', hidden: true })).toBeDisabled();
    view.rerender(<WorldFunctionControls {...props} />);
    expect(query.closest('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
    expect(await screen.findByRole('searchbox', { name: en.world.functions.search })).toHaveValue(
      'Retained on reconnect'
    );
  });
  it('keeps a streaming LIA conversation alive through a World reconnect', async () => {
    const ref = createRef<WorldFunctionHandle>();
    const props = {
      lng: 'en' as const,
      ownerId: 'owner',
      enabled: true,
      zone: 'arrival' as const,
      onOpen: vi.fn(),
      functionRef: ref,
    };
    const view = render(<WorldFunctionControls {...props} />);
    act(() => {
      ref.current?.openDestination({ kind: 'draft', draft: 'Hello' });
    });
    const input = await screen.findByRole('textbox', { name: 'Native chat draft' });
    expect(chat.mounted).toHaveBeenCalledTimes(1);
    view.rerender(<WorldFunctionControls {...props} suspended />);
    expect(input).toBeVisible();
    view.rerender(<WorldFunctionControls {...props} />);
    expect(screen.getByRole('textbox', { name: 'Native chat draft' })).toBe(input);
    expect(chat.mounted).toHaveBeenCalledTimes(1);
    expect(chat.cleaned).not.toHaveBeenCalled();
  });
  it('keeps the retained seated dashboard across Discuter, so its paid synthesis is asked once', async () => {
    const ref = createRef<WorldFunctionHandle>();
    const props = {
      lng: 'en' as const,
      ownerId: 'owner',
      zone: 'arrival' as const,
      onOpen: vi.fn(),
      functionRef: ref,
      dashboardSeatKey: 'confirmed-seat',
    };
    serveDashboardAct();
    const synthesis = textPurchases;
    const view = render(<WorldFunctionControls {...props} enabled />);
    act(() => {
      expect(ref.current?.openScene({ kind: 'workspace', id: 'dashboard' })).toBe(true);
    });
    const choice = await screen.findByRole('textbox', { name: 'Retained dashboard choice' });
    await waitFor(() => expect(synthesis()).toBe(1));
    fireEvent.change(choice, { target: { value: 'Seated choice' } });
    fireEvent.keyDown(choice, { key: 'Escape', code: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    // Discuter opens then closes: `enabled` toggles without remounting the host.
    view.rerender(<WorldFunctionControls {...props} enabled={false} />);
    view.rerender(<WorldFunctionControls {...props} enabled />);
    act(() => {
      expect(ref.current?.openScene({ kind: 'workspace', id: 'dashboard' })).toBe(true);
    });
    expect(await screen.findByRole('textbox', { name: 'Retained dashboard choice' })).toHaveValue(
      'Seated choice'
    );
    await act(async () => {
      // Drain any read a remount would have issued.
    });
    expect(synthesis()).toBe(1);
  });
  it('asks the dashboard synthesis once when a failed identity read hides and reveals it', async () => {
    const identity = { fails: false };
    serveDashboardAct();
    vi.mocked(apiClient.get).mockImplementation(async (endpoint: string) => {
      if (endpoint === DASHBOARD_INITIAL) return DASHBOARD_ACT;
      if (endpoint !== '/auth/me') return undefined;
      if (identity.fails) throw new Error('offline');
      return { id: 'owner', is_active: true };
    });
    const logged = vi.spyOn(logger, 'error').mockImplementation(() => {});
    const synthesis = textPurchases;
    const ref = createRef<WorldFunctionHandle>();
    try {
      render(
        <WorldAccountGuard ownerId="owner" lng="en">
          <WorldFunctionControls
            lng="en"
            ownerId="owner"
            enabled
            zone="arrival"
            onOpen={vi.fn()}
            functionRef={ref}
            dashboardSeatKey="confirmed-seat"
          />
        </WorldAccountGuard>
      );
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'LIA functions', hidden: true })).toBeEnabled()
      );
      act(() => {
        expect(ref.current?.openScene({ kind: 'workspace', id: 'dashboard' })).toBe(true);
      });
      const choice = await screen.findByRole('textbox', { name: 'Retained dashboard choice' });
      await waitFor(() => expect(synthesis()).toBe(1));
      fireEvent.change(choice, { target: { value: 'Kept while hidden' } });
      identity.fails = true;
      await act(async () => {
        fireEvent(window, new Event('focus'));
      });
      // The failed read withdraws the private subtree (its effects pause) …
      const retry = await screen.findByRole('button', { name: en.common.retry });
      expect(choice).not.toBeVisible();
      expect(logged).toHaveBeenCalled();
      identity.fails = false;
      await act(async () => {
        fireEvent.click(retry);
      });
      // … and the confirmed owner's return reveals it with its state and no second purchase.
      expect(await screen.findByRole('textbox', { name: 'Retained dashboard choice' })).toHaveValue(
        'Kept while hidden'
      );
      await act(async () => {
        // Drain any read the revealed effects would have issued.
      });
      expect(synthesis()).toBe(1);
    } finally {
      logged.mockRestore();
    }
  });
});

it('separates application preferences from usable activities without hiding either', async () => {
  render(
    <WorldFunctionControls lng="en" ownerId="owner" enabled zone="arrival" onOpen={vi.fn()} />
  );
  fireEvent.pointerDown(screen.getByRole('button', { name: 'LIA functions' }), {
    button: 0,
    ctrlKey: false,
  });
  fireEvent.click(await screen.findByRole('menuitem', { name: 'LIA functions' }));
  await screen.findByRole('searchbox');
  expect(screen.queryByRole('button', { name: 'Language' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: en.memories.settings.title })).toBeVisible();
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'LIA settings' }));
  await screen.findByRole('searchbox');
  expect(screen.getByRole('button', { name: 'Language' })).toBeVisible();
  expect(
    screen.queryByRole('button', { name: en.memories.settings.title })
  ).not.toBeInTheDocument();
});

it('rejects settings, administration and unavailable objects on the scene entry point', async () => {
  const ref = createRef<WorldFunctionHandle>();
  render(
    <WorldFunctionControls
      lng="en"
      ownerId="owner"
      enabled
      zone="home"
      onOpen={vi.fn()}
      functionRef={ref}
    />
  );
  for (const token of ['language', 'admin-users', 'open-loops'] as const) {
    act(() => {
      expect(ref.current?.openScene({ kind: 'native', token })).toBe(false);
    });
  }
  expect(ref.current?.canOpen({ kind: 'native', token: 'memories' })).toBe(true);
  expect(ref.current?.canOpen({ kind: 'command', id: 'weather' })).toBe(true);
  expect(ref.current?.canOpen({ kind: 'command', id: 'made-up' })).toBe(false);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await act(async () => {
    // Drain configuration only after all immediate scene-entry refusal checks.
  });
});

it('offers the radio object only under the native feature flag and never starts playback on discovery', async () => {
  const ref = createRef<WorldFunctionHandle>();
  const props = {
    lng: 'en' as const,
    ownerId: 'owner',
    enabled: true,
    zone: 'cafeteria' as const,
    onOpen: vi.fn(),
    functionRef: ref,
  };
  const view = render(<WorldFunctionControls {...props} />);
  expect(ref.current?.canOpen({ kind: 'widget', id: 'radio' })).toBe(false);
  act(() => {
    expect(ref.current?.openScene({ kind: 'widget', id: 'radio' })).toBe(false);
  });
  features.radioEnabled = true;
  view.rerender(<WorldFunctionControls {...props} />);
  expect(ref.current?.canOpen({ kind: 'widget', id: 'radio' })).toBe(true);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  view.rerender(<WorldFunctionControls {...props} suspended />);
  expect(ref.current?.canOpen({ kind: 'widget', id: 'radio' })).toBe(false);
  await act(async () => {
    // Drain configuration after preserving every synchronous feature-flag check.
  });
});
