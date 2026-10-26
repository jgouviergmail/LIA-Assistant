import { act, cleanup, renderHook } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import { SETTINGS_SECTION_REGISTRY } from '../settings-section-registry';
import { useSettingsSection } from '../useSettingsSection';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it('does not publish a late native panel after selection changed', async () => {
  const first = Promise.withResolvers<ReactElement>();
  const second = Promise.withResolvers<ReactElement>();
  vi.spyOn(SETTINGS_SECTION_REGISTRY.memories, 'render').mockReturnValue(first.promise);
  vi.spyOn(SETTINGS_SECTION_REGISTRY.interests, 'render').mockReturnValue(second.promise);
  const { result, rerender } = renderHook(
    ({ token }: { token: SettingsSectionToken }) => useSettingsSection(token, 'en', true),
    { initialProps: { token: 'memories' } }
  );
  rerender({ token: 'interests' });
  await act(async () => {
    first.resolve(<article>Obsolete panel</article>);
  });
  expect(result.current.element).toBeNull();
  expect(result.current.loading).toBe(true);
  await act(async () => {
    second.resolve(<article>Current panel</article>);
  });
  expect(result.current.element).toEqual(<article>Current panel</article>);
  expect(result.current.loading).toBe(false);
});
it('does not load a denied panel, and exposes a module failure without reflecting its details', async () => {
  const load = vi
    .spyOn(SETTINGS_SECTION_REGISTRY.memories, 'render')
    .mockRejectedValue(new Error('private internal fixture'));
  const { result, rerender } = renderHook(
    ({ enabled }) => useSettingsSection('memories', 'en', enabled),
    { initialProps: { enabled: false } }
  );
  expect(load).not.toHaveBeenCalled();
  rerender({ enabled: true });
  await act(async () => {
    await Promise.resolve();
  });
  expect(result.current).toEqual({ element: null, failed: true, loading: false });
});
