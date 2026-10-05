/**
 * The administrators' user table, declared as data.
 *
 * Every column used to be written out by hand — a header of fourteen lines and
 * a cell of seven, twenty-seven times — and the switches had drifted: three of
 * twenty-two were shown. The table now renders these lists, so a column is one
 * entry, the legend reads the same entries as the headers, and the switches
 * are checked against the backend's own declaration
 * (`apps/api/src/domains/users/admin_columns.py`, same names, same order).
 */

import {
  Activity,
  AtSign,
  BellRing,
  Blocks,
  BookOpenCheck,
  Bookmark,
  Brain,
  Bug,
  Clock,
  Database,
  Eye,
  Handshake,
  History,
  Image,
  Lightbulb,
  LogIn,
  MapPin,
  Mic,
  NotebookPen,
  PhoneCall,
  Plug,
  Repeat,
  Server,
  Smile,
  ScanFace,
  SmilePlus,
  Sparkles,
  UserSearch,
  Volume2,
  WandSparkles,
  type LucideIcon,
} from 'lucide-react';

/**
 * The per-account switches, in display order — the backend's
 * `ADMIN_USER_SWITCHES`, which a test holds equal to this list.
 */
export const ADMIN_USER_SWITCHES = [
  'memory_enabled',
  'psyche_enabled',
  'psyche_display_avatar',
  'habits_enabled',
  'journals_enabled',
  'journal_consolidation_enabled',
  'journal_consolidation_with_history',
  'voice_enabled',
  'speaking_avatar_enabled',
  'voice_mode_enabled',
  'phone_rich_context_enabled',
  'heartbeat_enabled',
  'interests_enabled',
  'relation_debrief_enabled',
  'image_generation_enabled',
  'image_generation_prompt_enhancement',
  'discovery_enabled',
  'peer_email_visible',
  'use_last_known_location',
  'login_notifications_enabled',
  'health_metrics_agents_enabled',
  'tokens_display_enabled',
  'debug_panel_enabled',
] as const;

export type AdminUserSwitch = (typeof ADMIN_USER_SWITCHES)[number];

/** One glyph per switch — a `Record`, so a switch without one does not compile. */
export const ADMIN_USER_SWITCH_ICONS: Record<AdminUserSwitch, LucideIcon> = {
  memory_enabled: Brain,
  psyche_enabled: Smile,
  psyche_display_avatar: SmilePlus,
  habits_enabled: Repeat,
  journals_enabled: NotebookPen,
  journal_consolidation_enabled: BookOpenCheck,
  journal_consolidation_with_history: History,
  voice_enabled: Volume2,
  speaking_avatar_enabled: ScanFace,
  voice_mode_enabled: Mic,
  phone_rich_context_enabled: PhoneCall,
  heartbeat_enabled: BellRing,
  interests_enabled: Lightbulb,
  relation_debrief_enabled: Handshake,
  image_generation_enabled: Image,
  image_generation_prompt_enhancement: WandSparkles,
  discovery_enabled: UserSearch,
  peer_email_visible: AtSign,
  use_last_known_location: MapPin,
  login_notifications_enabled: LogIn,
  health_metrics_agents_enabled: Activity,
  tokens_display_enabled: Eye,
  debug_panel_enabled: Bug,
};

/** The translated name of a switch. */
export function switchLabelKey(key: AdminUserSwitch): string {
  return `settings.admin.users.switches.${key}`;
}

/** What an account holds, counted — an icon header, a centred number. */
export const ADMIN_USER_COUNT_COLUMNS = [
  { key: 'active_connectors_count', icon: Plug, labelKey: 'connectors' },
  { key: 'memories_count', icon: Bookmark, labelKey: 'memories' },
  { key: 'interests_count', icon: Sparkles, labelKey: 'interests' },
  { key: 'skills_count', icon: Blocks, labelKey: 'skills' },
  { key: 'mcp_servers_count', icon: Server, labelKey: 'mcp_servers' },
  { key: 'scheduled_actions_count', icon: Clock, labelKey: 'scheduled_actions' },
  { key: 'rag_spaces_count', icon: Database, labelKey: 'rag_spaces' },
] as const;

export type AdminUserCount = (typeof ADMIN_USER_COUNT_COLUMNS)[number]['key'];

/**
 * What an account consumed — lifetime first, then the current billing cycle,
 * which is why « Cost per. » closes this group.
 */
export const ADMIN_USER_STAT_COLUMNS = [
  { key: 'total_messages', labelKey: 'messages_short', kind: 'count', weight: 'normal' },
  { key: 'total_tokens', labelKey: 'tokens', kind: 'count', weight: 'medium' },
  { key: 'total_google_api_requests', labelKey: 'google_api', kind: 'count', weight: 'normal' },
  { key: 'total_cost_eur', labelKey: 'cost', kind: 'eur', weight: 'bold' },
  { key: 'cycle_messages', labelKey: 'msgs_period', kind: 'count', weight: 'cycle' },
  { key: 'cycle_tokens', labelKey: 'tokens_period', kind: 'count', weight: 'cycle' },
  {
    key: 'cycle_google_api_requests',
    labelKey: 'google_api_period',
    kind: 'count',
    weight: 'cycle',
  },
  { key: 'cycle_cost_eur', labelKey: 'cost_period', kind: 'eur', weight: 'cycle-bold' },
] as const;

export type AdminUserStat = (typeof ADMIN_USER_STAT_COLUMNS)[number]['key'];

/** The header text of a `settings.admin.users.table.*` column. */
export function tableLabelKey(labelKey: string): string {
  return `settings.admin.users.table.${labelKey}`;
}
