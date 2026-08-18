'use client';

/**
 * Which shell the settings sections are rendered in.
 *
 * The master-detail settings page mounts ONE section in a pane, permanently
 * open; every other host (unit tests aside) stacks sections as accordion
 * items. The 50 section components are identical in both worlds — they render
 * `<SettingsSection>` and never know which shell they are in. This context is
 * how `SettingsSection` finds out, without threading a prop through 50 call
 * sites.
 *
 * The default is `accordion`: a section rendered outside any provider keeps
 * the behaviour it has always had.
 */

import { createContext, useContext } from 'react';

export type SettingsShellMode = 'accordion' | 'pane';

const SettingsShellModeContext = createContext<SettingsShellMode>('accordion');

/** Wraps a subtree whose sections must render for the given shell. */
export const SettingsShellModeProvider = SettingsShellModeContext.Provider;

/** The shell mode the nearest provider declares, `accordion` by default. */
export function useSettingsShellMode(): SettingsShellMode {
  return useContext(SettingsShellModeContext);
}
