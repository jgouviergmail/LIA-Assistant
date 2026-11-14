/**
 * Which settings sections exist on this instance NOW.
 *
 * A section whose routes the operator closed stayed in the rail, the overview
 * and the search, and opened on an error with a retry that could never work.
 * A section that shows a RECORD stays: learned habits and sandbox grants are
 * readable whatever the switch says (ADR-280, decision 2).
 *
 * The dock draws on every screen and asks nothing of its own (ADR-277, D7):
 * it reads the same verdicts from the layout's configuration, and what it
 * cannot know stays open.
 */
import { createElement, type PropsWithChildren } from 'react';
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const MOUNTED = {
  open_loops_enabled: true,
  habits_enabled: true,
  peers_enabled: true,
  python_sandbox_egress_enabled: true,
  live_enabled: true,
  avatar_enabled: true,
  radio_enabled: true,
  channels_enabled: true,
  journals_enabled: true,
  skills_enabled: true,
  rag_spaces_enabled: true,
  telephony_enabled: true,
};

const h = vi.hoisted(() => ({
  features: {} as Record<string, boolean>,
  capabilities: undefined as Record<string, { enabled: boolean; family: string }> | undefined,
  superuser: false,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'u1', is_superuser: h.superuser } }),
}));
vi.mock('@/hooks/useDebugPanelEnabled', () => ({
  useDebugPanelEnabled: () => ({ userAccessAvailable: false }),
}));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({ config: { features: h.features, capabilities: h.capabilities } }),
}));

import { appConfigFixture } from '@/__tests__/fixtures/app-config';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import {
  usePassiveSettingsAvailability,
  useSettingsAvailability,
} from '@/hooks/useSettingsAvailability';

const off = (...keys: string[]) =>
  Object.fromEntries(keys.map(key => [key, { enabled: false, family: 'x' }]));

const availability = () => renderHook(() => useSettingsAvailability()).result.current;

beforeEach(() => {
  h.features = { ...MOUNTED };
  h.capabilities = undefined;
  h.superuser = false;
});

describe('useSettingsAvailability', () => {
  it('lists every mounted section while the operator switched nothing off', () => {
    expect(availability()).toMatchObject({
      openLoopsEnabled: true,
      habitsEnabled: true,
      peersEnabled: true,
      sandboxEgressEnabled: true,
      liveEnabled: true,
      avatarEnabled: true,
      radioEnabled: true,
      channelsEnabled: true,
      psycheEnabled: true,
      journalsEnabled: true,
      skillsEnabled: true,
      mcpEnabled: true,
      ragSpacesEnabled: true,
      imageGenerationEnabled: true,
      telephonyEnabled: true,
    });
  });

  it('withdraws the sections whose routes the operator closed', () => {
    h.capabilities = off('open_loops', 'peers', 'live', 'avatar', 'radio');

    expect(availability()).toMatchObject({
      openLoopsEnabled: false,
      peersEnabled: false,
      liveEnabled: false,
      avatarEnabled: false,
      radioEnabled: false,
    });
  });

  it.each([
    ['channels', 'channelsEnabled'],
    ['psyche', 'psycheEnabled'],
    ['journals', 'journalsEnabled'],
    ['skills', 'skillsEnabled'],
    ['mcp', 'mcpEnabled'],
    ['rag_spaces', 'ragSpacesEnabled'],
    ['image_generation', 'imageGenerationEnabled'],
  ] as const)(
    'withdraws the section of %s once the operator switched it off, and no other',
    (capability, flag) => {
      // Every route these sections read refuses under the switch: the section
      // could show nothing but that refusal.
      h.capabilities = off(capability);

      const now = availability();

      expect(now[flag]).toBe(false);
      const others = [
        'channelsEnabled',
        'psycheEnabled',
        'journalsEnabled',
        'skillsEnabled',
        'mcpEnabled',
        'ragSpacesEnabled',
        'imageGenerationEnabled',
        'telephonyEnabled',
      ].filter(other => other !== flag);
      for (const other of others) expect(now, other).toHaveProperty(other, true);
    }
  );

  it.each([
    ['channels_enabled', 'channelsEnabled'],
    ['journals_enabled', 'journalsEnabled'],
    ['skills_enabled', 'skillsEnabled'],
    ['rag_spaces_enabled', 'ragSpacesEnabled'],
    ['telephony_enabled', 'telephonyEnabled'],
  ] as const)('lists no section the deployment does not mount (%s)', (ceiling, flag) => {
    h.features = { ...MOUNTED, [ceiling]: false };

    expect(availability()[flag]).toBe(false);
  });

  it('lists no personal MCP section where the deployment mounts no router for it', () => {
    // The MCP switch's ceiling is the instance's own servers; the personal
    // ones are mounted by another flag, and the map still says « offered ».
    h.features = { ...MOUNTED, mcp_user_enabled: false };
    h.capabilities = { mcp: { enabled: true, family: 'reach' } };

    expect(availability().mcpEnabled).toBe(false);

    h.features = { ...MOUNTED, mcp_user_enabled: true };

    expect(availability().mcpEnabled).toBe(true);
  });

  it('keeps the sections that show a record, whatever the switch says', () => {
    // What was learned, what was granted — and the number a person stored
    // with the history of their calls: the API serves those under the switch.
    h.capabilities = off('habits', 'python_sandbox_egress', 'telephony');

    expect(availability()).toMatchObject({
      habitsEnabled: true,
      sandboxEgressEnabled: true,
      telephonyEnabled: true,
    });
  });
});

describe('the device the page runs on', () => {
  /** Run with the Vibration API present, as on an Android phone. */
  function onVibratingDevice(run: () => void) {
    Object.defineProperty(navigator, 'vibrate', { value: vi.fn(), configurable: true });
    try {
      run();
    } finally {
      Reflect.deleteProperty(navigator, 'vibrate');
    }
  }
  const underLayout = () =>
    renderHook(() => usePassiveSettingsAvailability(), {
      wrapper: ({ children }: PropsWithChildren) =>
        createElement(AppConfigSeedContext.Provider, { value: null }, children),
    }).result.current;

  it('offers the haptic feedback only where the device can vibrate', () => {
    // jsdom has no Vibration API: the state of an iPhone, whose WebKit has none.
    expect(availability().hapticsSupported).toBe(false);

    onVibratingDevice(() => expect(availability().hapticsSupported).toBe(true));
  });

  it('is known to the dock too: a fact of the device is no doubt to read as open', () => {
    expect(underLayout().hapticsSupported).toBe(false);

    onVibratingDevice(() => expect(underLayout().hapticsSupported).toBe(true));
  });
});

describe('usePassiveSettingsAvailability — a surface that asks nothing of its own', () => {
  /** The layout's read of `/config`, as its provider hands it down. */
  const layoutConfig = (capabilities?: AppConfig['capabilities']): AppConfig =>
    appConfigFixture({ features: MOUNTED, capabilities });

  const passive = (seed: AppConfig | null) =>
    renderHook(() => usePassiveSettingsAvailability(), {
      wrapper: ({ children }: PropsWithChildren) =>
        createElement(AppConfigSeedContext.Provider, { value: seed }, children),
    }).result.current;

  /** Every verdict `/config` decides: all but the account, the debug grant and the device. */
  const OTHER_SOURCES = ['isSuperuser', 'debugUserAccess', 'hapticsSupported'];
  const verdicts = (availability: object) =>
    Object.fromEntries(
      Object.entries(availability).filter(([key]) => !OTHER_SOURCES.includes(key))
    );

  it('rules out what the layout configuration closes', () => {
    const now = passive(layoutConfig(off('journals', 'telephony')));

    expect(now).toMatchObject({
      journalsEnabled: false,
      // A record: its sections stay under the switch.
      telephonyEnabled: true,
      skillsEnabled: true,
      imageGenerationEnabled: true,
    });
  });

  it('answers as the settings page does once the configuration is there', () => {
    // ONE reading of `/config`: the dock cannot keep a section the rail dropped.
    h.capabilities = off('journals', 'psyche', 'image_generation', 'habits');

    expect(verdicts(passive(layoutConfig(h.capabilities)))).toEqual(verdicts(availability()));
  });

  it('rules nothing out before the configuration has answered', () => {
    // A filter ahead of the pane is more permissive than the pane, never less:
    // doubt hides no shortcut.
    const unknown = verdicts(passive(null));

    expect(Object.keys(unknown).length).toBeGreaterThan(10);
    for (const [flag, open] of Object.entries(unknown)) expect(open, flag).toBe(true);
  });

  it('carries the account role, and reads the debug grant it cannot know as open', () => {
    expect(passive(layoutConfig())).toMatchObject({ isSuperuser: false, debugUserAccess: true });

    h.superuser = true;

    expect(passive(layoutConfig())).toMatchObject({ isSuperuser: true, debugUserAccess: true });
  });
});
