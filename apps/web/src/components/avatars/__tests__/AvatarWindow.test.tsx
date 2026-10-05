import { act, cleanup as cleanupReact, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AvatarWindow } from '../AvatarWindow';
import { AvatarEngine } from '@/lib/avatars/engine';
import { mountAvatarEngine } from '@/lib/avatars/runtime';
import type { AvatarEngineDeps } from '@/lib/avatars/engine';
import type { AvatarSession } from '@/lib/avatars/types';
import { useAvatarWindowStore } from '@/stores/avatarWindowStore';
import enTranslations from '../../../../locales/en/translation.json';
import frTranslations from '../../../../locales/fr/translation.json';

const language = vi.hoisted(() => ({ value: 'en' }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === 'settings.avatar.window_cycle_size' || key === 'settings.avatar.window_stop'
        ? (language.value === 'fr' ? frTranslations : enTranslations).settings.avatar[
            key.split('.').at(-1) as 'window_cycle_size' | 'window_stop'
          ]
        : key,
  }),
}));

let cleanup = () => {};
beforeEach(() => {
  useAvatarWindowStore.setState({ size: 'sm', position: null });
});
afterEach(() => {
  cleanupReact();
  cleanup();
  vi.restoreAllMocks();
});
it.each([
  ['en', 'Change size'],
  ['fr', 'Changer la taille'],
])('cycles sizes through a named control in %s and keeps video muted', async (locale, label) => {
  language.value = locale;
  const attach = vi.fn();
  const deps: AvatarEngineDeps = {
    api: {
      start: vi.fn(() => new Promise<AvatarSession>(() => {})),
      heartbeat: vi.fn(),
      release: vi.fn(),
    },
    wire: () => {
      throw new Error('unused');
    },
    media: () => ({
      ready: false,
      clock: 0,
      quiet: true,
      video: vi.fn(),
      audio: vi.fn(),
      reset: vi.fn(),
      mute: vi.fn(),
      unlock: vi.fn(),
      attach,
      begin: vi.fn(),
    }),
  };
  const engine = new AvatarEngine(deps);
  engine.setDemand({
    account: 'account',
    credential: 'version',
    face: 'face',
    source: 'comments',
    connectSeconds: 15,
  });
  const unmount = mountAvatarEngine(engine);
  cleanup = () => {
    unmount();
    engine.dispose();
  };
  await act(async () => render(<AvatarWindow />));
  const surface = screen.getByRole('toolbar');
  expect(surface).toBeVisible();
  expect(
    screen.getByRole('button', {
      name:
        locale === 'fr'
          ? frTranslations.settings.avatar.window_stop
          : enTranslations.settings.avatar.window_stop,
    })
  ).toBeVisible();
  const resize = screen.getByRole('button', { name: label });
  for (const [size, width] of [
    ['md', 240],
    ['lg', 320],
    ['sm', 160],
  ] as const) {
    fireEvent.click(resize);
    expect(useAvatarWindowStore.getState().size).toBe(size);
    expect(resize).toHaveAttribute('title', `settings.avatar.window_${size}`);
    expect(surface.style.width).toContain(`${width}px`);
  }
  const video = surface.querySelector('video');
  expect(video?.muted).toBe(true);
  expect(video?.playsInline).toBe(true);
  expect(attach).toHaveBeenCalledWith(video);
  fireEvent.keyDown(surface, { key: 'ArrowRight' });
  expect(surface.style.left).not.toBe('');
});
