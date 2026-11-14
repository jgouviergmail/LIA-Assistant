'use client';

/**
 * useSettingsAvailability — the flags that decide which settings sections
 * exist for THIS account on THIS instance, resolved once for every surface
 * that lists sections: the settings shell (rail, overview, search) and the
 * « my shortcuts » picker (ADR-277). Extracted from the settings page so the
 * picker can never offer a section the shell would not show.
 *
 * `/config` has ONE reading here (`settingsCapabilityVerdicts`). The page asks
 * it of its own read; the surface that draws on every screen — the shortcuts
 * dock — asks it of the layout's (`usePassiveSettingsAvailability`), so that
 * a page costs no request more for carrying it (ADR-277, D7).
 */

import { useContext, useMemo } from 'react';

import { AppConfigSeedContext, useAppConfig, type AppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { capabilityAvailable, capabilityMounted } from '@/lib/capability-availability';
import { useHapticsSupported } from '@/lib/haptics';
import { peersAvailable } from '@/lib/peers/image-share';
import { radioAvailable } from '@/lib/radio/availability';
import { ragSpacesAvailable } from '@/lib/rag-spaces/availability';
import type { SettingsInstanceFlag, SettingsSearchAvailability } from '@/lib/settings-search';

/** What `/config` says of the capabilities the sections belong to. */
export type SettingsCapabilityVerdicts = Record<SettingsInstanceFlag, boolean>;

/**
 * The one reading of `/config` for the settings sections.
 *
 * The pane mounts nothing these verdicts rule out (`SettingsPaneFrame`), so a
 * flag here is the section's door: listed nowhere, loaded by nobody.
 *
 * @param config - The app configuration, possibly not loaded.
 * @returns One verdict per flag a section's gate can name.
 */
export function settingsCapabilityVerdicts(config: AppConfig | null): SettingsCapabilityVerdicts {
  return {
    // The effective state (the operator's switch included), read like the
    // radio's other surfaces: a section whose routes refuse is not offered.
    radioEnabled: radioAvailable(config),
    openLoopsEnabled: capabilityAvailable(config, 'open_loops'),
    peersEnabled: peersAvailable(config),
    liveEnabled: capabilityAvailable(config, 'live'),
    avatarEnabled: capabilityAvailable(config, 'avatar'),
    // These sections show a RECORD — what was learned, what was granted, the
    // number a person stored and the history of their calls — and stay under
    // the deployment flag whatever the switch says (ADR-280).
    habitsEnabled: capabilityMounted(config, 'habits'),
    sandboxEgressEnabled: capabilityMounted(config, 'python_sandbox_egress'),
    telephonyEnabled: capabilityMounted(config, 'telephony'),
    // The routes these sections read refuse under the operator's switch:
    // they could show nothing but that refusal.
    channelsEnabled: capabilityAvailable(config, 'channels'),
    psycheEnabled: capabilityAvailable(config, 'psyche'),
    journalsEnabled: capabilityAvailable(config, 'journals'),
    skillsEnabled: capabilityAvailable(config, 'skills'),
    mcpEnabled: capabilityAvailable(config, 'mcp'),
    ragSpacesEnabled: ragSpacesAvailable(config),
    imageGenerationEnabled: capabilityAvailable(config, 'image_generation'),
  };
}

/**
 * The availability a surface holds when it asks NOTHING of its own.
 *
 * It filters ahead of the pane, and a filter ahead of the decider is more
 * permissive than it, never less: what this surface cannot know — a
 * configuration that has not answered, the debug panel's grant — is read as
 * open. Doubt hides nothing. What it does know, it reads like the page: the
 * account's role, the device it runs on.
 *
 * @param config - The layout's read of the app configuration, null until it answers.
 * @param isSuperuser - Whether the account administers the instance.
 * @param hapticsSupported - Whether this device can vibrate.
 * @returns The verdicts of an answered configuration, everything open before.
 */
export function passiveSettingsAvailability(
  config: AppConfig | null,
  isSuperuser: boolean,
  hapticsSupported: boolean
): SettingsSearchAvailability {
  const verdicts = settingsCapabilityVerdicts(config);
  if (config === null) {
    for (const flag of Object.keys(verdicts) as SettingsInstanceFlag[]) verdicts[flag] = true;
  }
  return { isSuperuser, ...verdicts, hapticsSupported, debugUserAccess: true };
}

export function useSettingsAvailability(): SettingsSearchAvailability {
  const { user } = useAuth();
  const { userAccessAvailable } = useDebugPanelEnabled();
  const { config } = useAppConfig();
  const hapticsSupported = useHapticsSupported();
  const isSuperuser = !!user?.is_superuser;

  // Stable identity: `SettingsSearch` memoizes its whole index on this
  // object, and a fresh one per render would rebuild fifty entries every
  // keystroke. While `/config` is in flight the gated sections are genuinely
  // absent, and every consumer rebuilds by itself when the answer lands.
  return useMemo<SettingsSearchAvailability>(
    () => ({
      isSuperuser,
      ...settingsCapabilityVerdicts(config),
      hapticsSupported,
      debugUserAccess: userAccessAvailable,
    }),
    [isSuperuser, config, hapticsSupported, userAccessAvailable]
  );
}

/**
 * The same verdicts for the surface that draws on every screen: the layout's
 * read of `/config` (`AppConfigSeedContext`) and the account's role — no
 * request of its own.
 */
export function usePassiveSettingsAvailability(): SettingsSearchAvailability {
  const { user } = useAuth();
  const config = useContext(AppConfigSeedContext);
  const hapticsSupported = useHapticsSupported();
  const isSuperuser = !!user?.is_superuser;
  return useMemo(
    () => passiveSettingsAvailability(config, isSuperuser, hapticsSupported),
    [config, isSuperuser, hapticsSupported]
  );
}
