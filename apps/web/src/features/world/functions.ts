/** Native identities and availability remain the authority for private panels. */
import { buildSettingsShellModel, type SettingsShellSection } from '@/lib/settings-shell-model';
import { SETTINGS_SECTIONS, type SettingsSectionToken } from '@/lib/settings-sections';
import {
  SETTINGS_SEARCH_META,
  type SettingsGroupKey,
  type SettingsSearchAvailability,
  buildSettingsSearchIndex,
  matchSettingsSections,
} from '@/lib/settings-search';
import { buildStaticSlashCommands } from '@/lib/slash-commands';
import type { ZoneId } from './types';

export type FunctionPlace = ZoneId | 'transverse';
const GROUP_PLACES: Record<SettingsGroupKey, FunctionPlace> = {
  personalization: 'transverse',
  notifications_communication: 'arrival',
  security: 'transverse',
  voice_media: 'multimedia',
  connections_integrations: 'engineering',
  identity_memory: 'home',
  automation_tracking: 'engineering',
  extensions_data: 'library',
  users_access: 'transverse',
  ai_connectors: 'transverse',
  content_extensions: 'transverse',
  system: 'transverse',
};
const PLACEMENTS: Partial<Record<SettingsSectionToken, FunctionPlace>> = {
  'generated-assets': 'multimedia',
  memories: 'memory',
  'rag-spaces': 'library',
  skills: 'engineering',
  'mcp-servers': 'engineering',
  plugins: 'engineering',
  'open-loops': 'home',
  workboard: 'home',
  journals: 'transverse',
  'health-metrics': 'gym',
  interests: 'garden',
  habits: 'gym',
  'scheduled-actions': 'divination',
  reminders: 'home',
  'telephony-calls': 'phone',
  sms: 'restroom',
  meetings: 'meeting',
  'peer-connections': 'arrival',
  'user-consumption-export': 'transverse',
};
export function functionPlace(token: SettingsSectionToken): FunctionPlace | null {
  if (
    token.startsWith('admin-') ||
    SETTINGS_SECTIONS[token].tab === 'administration' ||
    SETTINGS_SEARCH_META[token].gate.kind === 'superuser'
  )
    return null;
  if (functionSurface(token) === 'settings') return 'transverse';
  return PLACEMENTS[token] ?? GROUP_PLACES[SETTINGS_SEARCH_META[token].group];
}
export function worldCatalogue(
  availability: SettingsSearchAvailability
): Array<SettingsShellSection & { place: FunctionPlace }> {
  return buildSettingsShellModel(availability).flatMap(tab =>
    tab.groups.flatMap(group =>
      group.sections.flatMap(section => {
        const place = functionPlace(section.token);
        return place ? [{ ...section, place }] : [];
      })
    )
  );
}

/** Native search scoring/keywords stay shared; world only narrows its audience. */
export function searchWorldCatalogue(
  availability: SettingsSearchAvailability,
  t: (key: string) => string,
  query: string
) {
  const catalogue = worldCatalogue(availability);
  if (!query.trim()) return catalogue;
  const matched = matchSettingsSections(buildSettingsSearchIndex(t, availability), query);
  return matched.flatMap(result => catalogue.filter(item => item.token === result.token));
}

const ACTION_PLACES: Readonly<Record<string, FunctionPlace>> = {
  agenda: 'divination',
  emails: 'phone',
  tasks: 'engineering',
  reminders: 'home',
  'new-reminder': 'divination',
  'new-routine': 'divination',
  weather: 'divination',
  'weather-weekend': 'divination',
  news: 'cafeteria',
  resume: 'transverse',
};
export function worldActions(t: (key: string) => string) {
  return buildStaticSlashCommands(t)
    .filter(command => command.kind === 'conversational')
    .map(command => ({ ...command, place: ACTION_PLACES[command.id] ?? 'arrival' }));
}

/** Presentation only: native availability and endpoints still own authority. */
const ACTIVITIES: ReadonlySet<SettingsSectionToken> = new Set([
  'skills',
  'mcp-servers',
  'plugins',
  'generated-assets',
  'telephony-calls',
  'psyche',
  'memories',
  'interests',
  'open-loops',
  'habits',
  'peer-connections',
  'scheduled-actions',
  'reminders',
  'journals',
  'health-metrics',
  'rag-spaces',
  'meetings',
  'sms',
  'workboard',
  'user-consumption-export',
]);
export type FunctionSurface = 'activity' | 'settings';
export function functionSurface(token: SettingsSectionToken): FunctionSurface {
  return ACTIVITIES.has(token) ? 'activity' : 'settings';
}
