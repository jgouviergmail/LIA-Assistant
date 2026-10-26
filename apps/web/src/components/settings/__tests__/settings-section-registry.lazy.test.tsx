import { expect, it, vi } from 'vitest';

const loaded = vi.hoisted(() => [] as string[]);
vi.mock('../MemorySettings', () => {
  loaded.push('memory');
  return { MemorySettings: () => null };
});
vi.mock('../AdminUsersSection', () => {
  loaded.push('admin');
  return { default: () => null };
});
import { SETTINGS_SECTION_REGISTRY } from '../settings-section-registry';

it('loads only the native panel chosen by the user, without importing administrative panels', async () => {
  expect(loaded).toEqual([]);
  const section = await SETTINGS_SECTION_REGISTRY.memories.render('fr');
  expect(loaded).toEqual(['memory']);
  expect(section.props).toMatchObject({ lng: 'fr' });
});
