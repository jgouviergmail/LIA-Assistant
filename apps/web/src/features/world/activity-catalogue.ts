/** Closed, public action vocabulary. These are identities, never executable user content. */
import type { SettingsSectionToken } from '@/lib/settings-sections';
import type { GeneratedAssetTab } from '@/types/generated-assets';
import type { CabinetId } from './game-catalogue';

export type WorldWorkspace =
  | 'dashboard'
  | 'relations'
  | 'meetings'
  | 'workboard'
  | 'alerts'
  | 'sms'
  | 'registers';
export type SceneActivity =
  | { kind: 'arcade'; id: CabinetId }
  | { kind: 'world'; id: 'appearance' }
  | { kind: 'native'; token: SettingsSectionToken }
  | { kind: 'command'; id: string }
  | { kind: 'compose'; id: 'image' | 'call' }
  | { kind: 'gallery'; tab: GeneratedAssetTab }
  | { kind: 'workspace'; id: WorldWorkspace }
  | { kind: 'widget'; id: 'radio' };
export const ACTIVITY_CATALOGUE = {
  'arcade-tic-tac-toe': { kind: 'arcade', id: 'arcade-tic-tac-toe' },
  'arcade-four-in-row': { kind: 'arcade', id: 'arcade-four-in-row' },
  'arcade-reversi': { kind: 'arcade', id: 'arcade-reversi' },
  appearance: { kind: 'world', id: 'appearance' },
  knowledge: { kind: 'native', token: 'rag-spaces' },
  'open-loops': { kind: 'native', token: 'open-loops' },
  workboard: { kind: 'workspace', id: 'workboard' },
  relations: { kind: 'workspace', id: 'relations' },
  tasks: { kind: 'command', id: 'tasks' },
  memories: { kind: 'native', token: 'memories' },
  profile: { kind: 'native', token: 'psyche' },
  assets: { kind: 'gallery', tab: 'images' },
  'asset-images': { kind: 'gallery', tab: 'images' },
  'asset-documents': { kind: 'gallery', tab: 'documents' },
  'asset-screenshots': { kind: 'gallery', tab: 'screenshots' },
  'asset-bookmarks': { kind: 'gallery', tab: 'bookmarks' },
  'generate-image': { kind: 'compose', id: 'image' },
  weather: { kind: 'command', id: 'weather' },
  mail: { kind: 'command', id: 'emails' },
  agenda: { kind: 'command', id: 'agenda' },
  news: { kind: 'command', id: 'news' },
  phone: { kind: 'compose', id: 'call' },
  'recent-calls': { kind: 'native', token: 'telephony-calls' },
  sms: { kind: 'workspace', id: 'sms' },
  reminders: { kind: 'native', token: 'reminders' },
  routines: { kind: 'native', token: 'scheduled-actions' },
  interests: { kind: 'native', token: 'interests' },
  habits: { kind: 'native', token: 'habits' },
  health: { kind: 'native', token: 'health-metrics' },
  journals: { kind: 'native', token: 'journals' },
  peers: { kind: 'native', token: 'peer-connections' },
  meetings: { kind: 'workspace', id: 'meetings' },
  skills: { kind: 'native', token: 'skills' },
  mcp: { kind: 'native', token: 'mcp-servers' },
  plugins: { kind: 'native', token: 'plugins' },
  radio: { kind: 'widget', id: 'radio' },
} as const satisfies Readonly<Record<string, SceneActivity>>;
export type ActivityKey = keyof typeof ACTIVITY_CATALOGUE;
export function authoredActivity(key: string | undefined): SceneActivity | null {
  return key && Object.hasOwn(ACTIVITY_CATALOGUE, key)
    ? ACTIVITY_CATALOGUE[key as ActivityKey]
    : null;
}
