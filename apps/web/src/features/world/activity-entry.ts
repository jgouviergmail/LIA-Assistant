import type { SettingsSectionToken } from '@/lib/settings-sections';
import type { GeneratedAssetTab } from '@/types/generated-assets';
import type { SceneActivity, WorldWorkspace } from './activity-catalogue';
import type { AppConfig } from '@/hooks/useAppConfig';
import { SETTINGS_SEARCH_META } from '@/lib/settings-search';
import { worldActions } from './functions';
import type { BoardFilters } from '@/types/workboard';
import type { DashboardDestination } from '@/components/dashboard/DashboardNavigation';
import { CABINET_GAMES, type CabinetId } from './game-catalogue';

export const WORKSPACE_SELECTION = {
  dashboard: 'world-dashboard',
  registers: 'world-registers',
  relations: 'world-relations',
  meetings: 'world-meetings',
  workboard: 'world-workboard',
  alerts: 'world-alerts',
  sms: 'world-sms',
} as const satisfies Record<WorldWorkspace, string>;
export type WorkspaceSelection = (typeof WORKSPACE_SELECTION)[WorldWorkspace];
export type WorldSelection =
  | SettingsSectionToken
  | WorkspaceSelection
  | 'lia'
  | 'lia-menu'
  | 'catalogue'
  | 'place'
  | 'world-peers'
  | 'configuration'
  | 'world-radio'
  | 'world-arcade'
  | 'world-avatar';
export interface ActivityEntry {
  cabinet?: CabinetId;
  selection: WorldSelection;
  draft?: string;
  tab?: GeneratedAssetTab;
  meetingId?: string;
  workboardFilters?: BoardFilters;
  ticketId?: string;
  smsMessageId?: string;
}
export function dashboardEntry(destination: DashboardDestination): ActivityEntry {
  switch (destination.kind) {
    case 'settings':
      return { selection: destination.token ?? 'configuration' };
    case 'draft':
      return { selection: 'lia', draft: destination.draft };
    case 'workboard':
      return {
        selection: WORKSPACE_SELECTION.workboard,
        workboardFilters: destination.filters,
        ticketId: destination.ticketId,
      };
    case 'meeting':
      return { selection: WORKSPACE_SELECTION.meetings, meetingId: destination.id };
    case 'gallery':
      return { selection: 'generated-assets', tab: destination.tab };
    case 'registers':
      return { selection: WORKSPACE_SELECTION.registers };
    case 'sms':
      return { selection: WORKSPACE_SELECTION.sms, smsMessageId: destination.messageId };
  }
}
type Translate = (key: string, values?: Record<string, unknown>) => string;
export function workspaceFromSelection(selection: WorldSelection): WorldWorkspace | null {
  for (const id of Object.keys(WORKSPACE_SELECTION) as WorldWorkspace[])
    if (WORKSPACE_SELECTION[id] === selection) return id;
  return null;
}
/** Project one authorized activity identity into its stable modal/non-modal hosts. */
export function activityPresentation(selection: WorldSelection | null, authorized: boolean) {
  const open = authorized && selection !== null;
  const conversation = selection === 'lia';
  const dashboardOpen = open && selection === WORKSPACE_SELECTION.dashboard;
  return {
    open,
    conversation,
    dashboardOpen,
    nativeOpen: open && !dashboardOpen,
    dockActive: open && conversation,
  };
}
export function activityEntry(activity: SceneActivity | 'lia', t: Translate): ActivityEntry {
  if (activity === 'lia') return { selection: 'lia-menu' };
  switch (activity.kind) {
    case 'arcade':
      return { selection: 'world-arcade', cabinet: activity.id };
    case 'world':
      return { selection: 'world-avatar' };
    case 'native':
      return { selection: activity.token };
    case 'gallery':
      return { selection: 'generated-assets', tab: activity.tab };
    case 'workspace':
      return { selection: WORKSPACE_SELECTION[activity.id] };
    case 'widget':
      return { selection: 'world-radio' };
    case 'compose':
      return { selection: 'lia', draft: t('world.activities.' + activity.id + '_draft') };
    case 'command':
      return {
        selection: 'lia',
        draft: worldActions(t).find(item => item.id === activity.id)?.insertText,
      };
  }
}
export function activityTitle(activity: SceneActivity, t: Translate): string {
  switch (activity.kind) {
    case 'arcade':
      return t('world.arcade.games.' + CABINET_GAMES[activity.id] + '.title');
    case 'world':
      return t('world.avatar.change');
    case 'native':
      return t(SETTINGS_SEARCH_META[activity.token].titleKey);
    case 'gallery':
      return t('world.activities.gallery', {
        family: t('settings.generated_assets.family.' + activity.tab),
      });
    case 'workspace':
      return t(activity.id === 'registers' ? 'registers.title' : 'world.activities.' + activity.id);
    case 'widget':
      return t('radio.page.title');
    case 'compose':
      return t('world.activities.' + activity.id);
    case 'command':
      return worldActions(t).find(item => item.id === activity.id)?.label ?? '';
  }
}
export function workspaceAvailable(id: WorldWorkspace, config: AppConfig | null): boolean {
  const gates: Partial<Record<WorldWorkspace, boolean | undefined>> = {
    meetings: config?.features.meetings_enabled,
    workboard: config?.features.workboard_enabled,
    sms: config?.features.sms_enabled,
  };
  return Object.hasOwn(gates, id) ? gates[id] === true : true;
}

export function activityAvailable(
  activity: SceneActivity | 'lia',
  policy: {
    native: ReadonlySet<SettingsSectionToken>;
    commands: ReadonlySet<string>;
    radio: boolean;
    config: AppConfig | null;
  }
): boolean {
  if (activity === 'lia') return true;
  switch (activity.kind) {
    case 'arcade':
      return policy.config?.features.world_arcade_enabled === true;
    case 'world':
      return true;
    case 'native':
      return policy.native.has(activity.token);
    case 'gallery':
      return (
        policy.native.has('generated-assets') &&
        (activity.tab !== 'bookmarks' || policy.config?.features.bookmarks_enabled === true)
      );
    case 'workspace':
      return workspaceAvailable(activity.id, policy.config);
    case 'widget':
      return policy.radio;
    case 'compose':
      return true;
    case 'command':
      return policy.commands.has(activity.id);
  }
}

/** Activity discovery opens the real workspace; the separate settings menu keeps native configuration. */
export function catalogueSelection(selection: WorldSelection, settings: boolean): WorldSelection {
  if (settings) return selection;
  const workspace = {
    meetings: 'world-meetings',
    workboard: 'world-workboard',
    sms: 'world-sms',
  } as const;
  return Object.hasOwn(workspace, selection)
    ? workspace[selection as keyof typeof workspace]
    : selection;
}
