import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@/lib/auth';
import { makeUser } from '@/__tests__/factories';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { createRef } from 'react';
import { WorldFunctionControls, type WorldFunctionHandle } from '../WorldFunctionControls';
import { WorldAccountGuard } from '../WorldAccountGuard';
import apiClient from '@/lib/api-client';

vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get: vi.fn() },
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
});
describe('private native function controls', () => {
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
    vi.mocked(apiClient.get).mockResolvedValueOnce({ id: 'owner', is_active: true });
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
    expect(query).not.toBeVisible();
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
    expect(query).not.toBeVisible();
    expect(screen.getByRole('button', { name: 'LIA functions' })).toBeDisabled();
    view.rerender(<WorldFunctionControls {...props} />);
    expect(await screen.findByRole('searchbox', { name: en.world.functions.search })).toHaveValue(
      'Retained on reconnect'
    );
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
