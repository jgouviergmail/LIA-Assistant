import { StrictMode } from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AvatarProvider } from '../AvatarProvider';
import { useLiveStore } from '@/stores/liveStore';
import { avatarEngine } from '@/lib/avatars/runtime';

const fixture = vi.hoisted(() => ({
  user: { id: 'account', voice_enabled: true },
  config: {
    available: true,
    enabled: true,
    connected: true,
    face_id: 'face',
    connector_version: 'version',
    session_length_seconds: 3600,
    connect_timeout_seconds: 15,
  },
  start: vi.fn(async () => ({
    session_token: 'fixture',
    lease_id: 'lease',
    ice_servers: [],
    max_session_seconds: 3600,
  })),
  close: vi.fn(),
  skip: vi.fn(),
  release: vi.fn(async () => true),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: fixture.user }) }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: () => ({ data: fixture.config }) }));
vi.mock('@/lib/avatars/api', () => ({
  avatarApi: { start: fixture.start, heartbeat: vi.fn(async () => {}), release: fixture.release },
}));
vi.mock('@/lib/avatars/simli-transport', () => ({
  SimliTransport: class {
    async connect() {}
    close = fixture.close;
    skip = fixture.skip;
    sendPcm() {
      return true;
    }
  },
}));
vi.mock('@/lib/avatars/browser-media', () => ({
  BrowserAvatarMedia: class {
    ready = true;
    quiet = true;
    clock = 0;
    audio() {}
    video() {}
    reset() {}
    mute() {}
    attach() {}
    begin() {}
    async unlock() {}
  },
}));
async function settle() {
  await act(async () => {
    for (let n = 0; n < 30; n++) await Promise.resolve();
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  useLiveStore.getState().reset();
  fixture.user = { id: 'account', voice_enabled: true };
  fixture.config.enabled = true;
});
afterEach(() => {
  useLiveStore.getState().reset();
  vi.restoreAllMocks();
});

it('StrictMode and preference refreshes retain one owned connection through Live activation and close at standby', async () => {
  const view = render(
    <StrictMode>
      <AvatarProvider>Chat</AvatarProvider>
    </StrictMode>
  );
  await settle();
  expect(fixture.start).toHaveBeenCalledOnce();
  const engine = avatarEngine();
  expect(engine?.ready).toBe(true);
  act(() => useLiveStore.getState().begin(null, 'direct'));
  fixture.user.voice_enabled = false;
  view.rerender(
    <StrictMode>
      <AvatarProvider>Chat</AvatarProvider>
    </StrictMode>
  );
  await settle();
  expect(avatarEngine()).toBe(engine);
  expect(fixture.close).not.toHaveBeenCalled();
  act(() => {
    useLiveStore.getState().begin('live', 'direct');
    useLiveStore.getState().apply('minted');
  });
  await settle();
  expect(fixture.start).toHaveBeenCalledOnce();
  act(() => useLiveStore.getState().enterStandby({ at: Date.now(), deadline: Date.now() + 60000 }));
  await settle();
  expect(screen.queryByRole('toolbar')).toBeNull();
  expect(fixture.close).toHaveBeenCalledOnce();
  view.unmount();
  await settle();
});

it('a cold Live request displays preparation without minting an unauthorized comments session', async () => {
  fixture.user.voice_enabled = false;
  const view = render(<AvatarProvider>Chat</AvatarProvider>);
  await settle();
  act(() => useLiveStore.getState().begin(null));
  await settle();
  expect(screen.getByRole('toolbar')).toBeVisible();
  expect(fixture.start).not.toHaveBeenCalled();
  act(() => useLiveStore.getState().finish('error', 'fixture_failure'));
  await settle();
  expect(screen.queryByRole('toolbar')).toBeNull();
  expect(fixture.start).not.toHaveBeenCalled();
  view.unmount();
  await settle();
});

it('a consent revocation during preparation closes the held owner without recreating it', async () => {
  const view = render(<AvatarProvider>Chat</AvatarProvider>);
  await settle();
  act(() => useLiveStore.getState().begin(null));
  fixture.config = { ...fixture.config, enabled: false };
  view.rerender(<AvatarProvider>Chat</AvatarProvider>);
  await settle();
  expect(fixture.close).toHaveBeenCalledOnce();
  expect(fixture.start).toHaveBeenCalledOnce();
  expect(avatarEngine()?.permitted).toBe(false);
  view.unmount();
  await settle();
});
