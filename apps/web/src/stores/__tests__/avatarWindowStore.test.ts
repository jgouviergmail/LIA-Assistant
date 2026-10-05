import { beforeEach, expect, it } from 'vitest';
import { AVATAR_WINDOW_STORAGE_KEY, useAvatarWindowStore } from '../avatarWindowStore';

beforeEach(() => {
  localStorage.clear();
  useAvatarWindowStore.setState({ size: 'sm', position: null });
});

async function restore(state: unknown) {
  localStorage.setItem(AVATAR_WINDOW_STORAGE_KEY, JSON.stringify({ state, version: 0 }));
  await useAvatarWindowStore.persist.rehydrate();
  return useAvatarWindowStore.getState();
}

it.each([null, false, 'bad', 4])('rejects a non-object persisted geometry (%s)', async state => {
  expect(await restore(state)).toMatchObject({ size: 'sm', position: null });
});

it.each([
  {},
  { size: 'unknown' },
  { size: 'md', position: false },
  { size: 'lg', position: 'bad' },
  { position: {} },
  { position: { xPct: 1 } },
  { position: { yPct: 1 } },
  { position: { xPct: '1', yPct: 2 } },
  { position: { xPct: 1, yPct: '2' } },
  { position: { xPct: null, yPct: 2 } },
])('drops damaged positions while restoring a supported size: %j', async state => {
  const result = await restore(state);
  expect(result.position).toBeNull();
  expect(result.size).toBe(
    'size' in state && ['md', 'lg'].includes(String(state.size)) ? state.size : 'sm'
  );
});

it('clamps off-screen coordinates and rejects non-finite in-memory stored values', async () => {
  expect(
    await restore({
      size: 'lg',
      position: { xPct: -20, yPct: 150 },
      enabled: true,
      token: 'test-only',
    })
  ).toMatchObject({ size: 'lg', position: { xPct: 0, yPct: 100 } });
  // JSON cannot encode NaN/Infinity, but another storage adapter can return them.
  const merge = useAvatarWindowStore.persist.getOptions().merge!;
  for (const position of [
    { xPct: NaN, yPct: 20 },
    { xPct: 10, yPct: Infinity },
  ]) {
    expect(merge({ size: 'md', position }, useAvatarWindowStore.getState()).position).toBeNull();
  }
  expect(useAvatarWindowStore.getState()).not.toHaveProperty('enabled');
  expect(useAvatarWindowStore.getState()).not.toHaveProperty('token');
});

it('persists only display geometry and restores working setters', async () => {
  useAvatarWindowStore.getState().setSize('md');
  useAvatarWindowStore.getState().setPosition({ xPct: 25, yPct: 75 });
  const stored = JSON.parse(localStorage.getItem(AVATAR_WINDOW_STORAGE_KEY)!);
  expect(stored.state).toEqual({ size: 'md', position: { xPct: 25, yPct: 75 } });
  const result = await restore(stored.state);
  expect(result).toMatchObject(stored.state);
  expect(typeof result.setSize).toBe('function');
});

it('does not publish a new state for an unchanged placement', () => {
  useAvatarWindowStore.getState().setPosition({ xPct: 20, yPct: 30 });
  const saved = useAvatarWindowStore.getState();
  saved.setPosition({ xPct: 20, yPct: 30 });
  expect(useAvatarWindowStore.getState()).toBe(saved);
});
