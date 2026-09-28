/**
 * Single source of truth for the editorial landing narrative (chapters 01-06
 * plus the basics band). Every detailed feature card of the former features
 * wall is re-parented here — never deleted — and rendered inside the
 * per-chapter expandable catalogs, reusing the translated
 * `landing.features.<key>.{title,description}` copy in all 6 locales.
 *
 * The most distinctive capabilities lead each catalog. Its compact visual
 * index opens one complete description at a time; the original copy is never
 * shortened to fit a card. The hint under each chapter derives its count
 * from the catalog — never typed into the copy.
 *
 * ANTI-REGRESSION CONTRACT: `REQUIRED_FEATURE_KEYS` is the canonical
 * inventory of detailed feature cards. The guard test
 * `__tests__/editorial-content-coverage.test.ts` asserts that the chapter
 * catalogs plus the basics catalog cover it exactly (no loss, no duplicate).
 * Removing a feature from the landing therefore requires a deliberate edit
 * of the contract, never an accidental omission.
 */

import type { LucideIcon } from 'lucide-react';
import type { ProductSceneId } from '../demo/scenes';
import {
  CloudSun,
  Activity,
  AppWindow,
  AudioLines,
  BellRing,
  Blocks,
  BookOpen,
  Bot,
  Calculator,
  Brain,
  CalendarClock,
  Compass,
  Gauge,
  Globe,
  Handshake,
  Heart,
  HelpCircle,
  Bookmark,
  Eye,
  Flame,
  LayoutTemplate,
  MailCheck,
  PhoneIncoming,
  ShieldAlert,
  Tag,
  Timer,
  UserCheck,
  Workflow,
  KeyRound,
  FileOutput,
  ImagePlus,
  LayoutGrid,
  Library,
  Lightbulb,
  Lock,
  Mail,
  MessageCircle,
  MessageSquareText,
  Mic,
  Monitor,
  MousePointerClick,
  Palette,
  Paperclip,
  PenTool,
  PhoneCall,
  Package,
  Puzzle,
  ShieldCheck,
  Smartphone,
  TabletSmartphone,
  Smile,
  Star,
  Sunrise,
  Terminal,
  Users,
  Repeat,
  Radio,
  ClipboardList,
  SquareKanban,
} from 'lucide-react';

export type ChapterId = 'act' | 'know' | 'anticipate' | 'control' | 'grow' | 'connect';

export interface ChapterConfig {
  id: ChapterId;
  /** Shared functional illustration from the hero demonstration. */
  scene: ProductSceneId;
  /** i18n suffix under `landing.chapters.` (c1..c6). */
  key: 'c1' | 'c2' | 'c3' | 'c4' | 'c5' | 'c6';
  /** Anchor id (chapter rail + deep links). */
  anchor: string;
  num: string;
  /** Psyche mood carried by the chapter's title bubble — intentional per
   *  chapter: playful on differentiation, composed on trust (c2/c4). */
  mood: string;
  /** Benefit count (b1..bN keys must exist in all locales). */
  benefits: 3 | 4;
  /** Detailed feature cards re-parented under this chapter. */
  catalog: readonly string[];
  /** Alternating card background for visual rhythm. */
  tinted: boolean;
}

export const CHAPTERS: readonly ChapterConfig[] = [
  {
    id: 'act',
    scene: 'decision',
    key: 'c1',
    anchor: 'chapter-act',
    num: '01',
    mood: '😏',
    benefits: 4,
    catalog: [
      'multi_agent',
      'telephony',
      'live_voice',
      'meetings',
      'browser_control',
      'document_generation',
      'computed_answers',
      'telephony_callback',
      'meeting_templates',
      'image_generation',
      'excalidraw',
      'smart_home',
      'natural_language',
      'rich_responses',
      'chat_sync',
      'email_share',
      'generated_files',
    ],
    tinted: false,
  },
  {
    id: 'know',
    scene: 'day',
    key: 'c2',
    anchor: 'chapter-know',
    num: '02',
    mood: '🙂',
    benefits: 3,
    catalog: [
      'memory',
      'journals',
      'personal_crm',
      'personal_radio',
      'psyche',
      'briefing',
      'bookmarks',
      'personalities',
      'mood_face',
      'self_knowledge',
    ],
    tinted: true,
  },
  {
    id: 'anticipate',
    scene: 'watch',
    key: 'c3',
    anchor: 'chapter-anticipate',
    num: '03',
    mood: '😏',
    benefits: 3,
    catalog: [
      'workboard_delegation',
      'conditional_routines',
      'proactive',
      'proactive_wake',
      'proactive_moments',
      'habits',
      'habits_lifecycle',
      'workboard',
      'interests',
      'reminders_scheduling',
      'health_metrics',
    ],
    tinted: false,
  },
  {
    id: 'control',
    scene: 'call',
    key: 'c4',
    anchor: 'chapter-control',
    num: '04',
    mood: '🙂',
    benefits: 4,
    catalog: ['control', 'privacy', 'usage_limits', 'native_apps'],
    tinted: true,
  },
  {
    id: 'grow',
    scene: 'research',
    key: 'c5',
    anchor: 'chapter-grow',
    num: '05',
    mood: '😏',
    benefits: 3,
    catalog: [
      'sub_agents',
      'rag_spaces',
      'skills',
      'mail_label_spaces',
      'mcp_apps',
      'mcp',
      'plugins',
      'devops_cli',
    ],
    tinted: false,
  },
  {
    id: 'connect',
    scene: 'relay',
    key: 'c6',
    anchor: 'chapter-connect',
    num: '06',
    mood: '🙂',
    benefits: 3,
    catalog: ['peers', 'peer_shares', 'peer_safety'],
    tinted: true,
  },
] as const;

/** Commodity cards living in the basics band's own catalog. */
export const BASICS_CATALOG: readonly string[] = [
  'web_intelligence',
  'connected_services',
  'multichannel',
  'voice_mode',
  'environment',
  'attachments',
  'languages',
  'responsive',
  'simplicity',
  'themes',
] as const;

/** Chips shown in the basics band (i18n suffixes under `landing.basics.`). */
export const BASICS_CHIPS: readonly { emoji: string; key: string }[] = [
  { emoji: '✉️', key: 'chip_emails' },
  { emoji: '📅', key: 'chip_calendar' },
  { emoji: '👥', key: 'chip_contacts' },
  { emoji: '☑️', key: 'chip_tasks' },
  { emoji: '📂', key: 'chip_files' },
  { emoji: '🌦️', key: 'chip_weather' },
  { emoji: '🗺️', key: 'chip_places' },
  { emoji: '🔎', key: 'chip_search' },
  { emoji: '📎', key: 'chip_attachments' },
  { emoji: '🎙️', key: 'chip_voice' },
  { emoji: '🌍', key: 'chip_languages' },
  { emoji: '📱', key: 'chip_channels' },
  { emoji: '🎨', key: 'chip_themes' },
] as const;

/**
 * Canonical inventory of the detailed feature cards inherited from the
 * former features wall. The coverage guard test enforces that the chapter
 * catalogs + basics catalog form an exact partition of this set.
 */
export const REQUIRED_FEATURE_KEYS: readonly string[] = [
  // conversation
  'natural_language',
  'multi_agent',
  'rich_responses',
  'chat_sync',
  'email_share',
  'generated_files',
  'multichannel',
  'languages',
  // personality & memory
  'memory',
  'bookmarks',
  'personal_crm',
  'peers',
  'peer_shares',
  'peer_safety',
  'personalities',
  'psyche',
  'mood_face',
  'self_knowledge',
  'journals',
  // proactivity & automation
  'briefing',
  'personal_radio',
  'proactive',
  'proactive_wake',
  'proactive_moments',
  'interests',
  'habits',
  'habits_lifecycle',
  'reminders_scheduling',
  'conditional_routines',
  'workboard',
  'workboard_delegation',
  'telephony',
  'telephony_callback',
  'live_voice',
  'meetings',
  'meeting_templates',
  'skills',
  'health_metrics',
  // creation & media
  'excalidraw',
  'image_generation',
  'document_generation',
  'attachments',
  'mcp_apps',
  // extensibility & power
  'plugins',
  'mcp',
  'rag_spaces',
  'mail_label_spaces',
  'sub_agents',
  'browser_control',
  'computed_answers',
  'devops_cli',
  // responsible & simple
  'control',
  'usage_limits',
  'privacy',
  'native_apps',
  'responsive',
  'simplicity',
  'themes',
  // former hero cards
  'connected_services',
  'environment',
  'smart_home',
  'web_intelligence',
  'voice_mode',
] as const;

/** Icon per feature card, inherited from the former features wall. */
export const FEATURE_ICONS: Record<string, LucideIcon> = {
  natural_language: MessageSquareText,
  multi_agent: Bot,
  rich_responses: LayoutGrid,
  chat_sync: MessageCircle,
  email_share: Mail,
  generated_files: FileOutput,
  multichannel: MessageCircle,
  languages: Globe,
  memory: Brain,
  bookmarks: Bookmark,
  personal_crm: Users,
  peers: Handshake,
  peer_shares: KeyRound,
  peer_safety: ShieldAlert,
  personalities: Smile,
  psyche: Heart,
  mood_face: Eye,
  self_knowledge: HelpCircle,
  journals: BookOpen,
  briefing: Sunrise,
  personal_radio: Radio,
  proactive: BellRing,
  proactive_wake: MailCheck,
  proactive_moments: Timer,
  interests: Star,
  habits: Repeat,
  habits_lifecycle: Flame,
  reminders_scheduling: CalendarClock,
  conditional_routines: Workflow,
  workboard: SquareKanban,
  workboard_delegation: UserCheck,
  telephony: PhoneCall,
  telephony_callback: PhoneIncoming,
  live_voice: AudioLines,
  meetings: ClipboardList,
  meeting_templates: LayoutTemplate,
  skills: Blocks,
  health_metrics: Activity,
  excalidraw: PenTool,
  image_generation: ImagePlus,
  document_generation: FileOutput,
  attachments: Paperclip,
  mcp_apps: AppWindow,
  mcp: Puzzle,
  plugins: Package,
  rag_spaces: Library,
  mail_label_spaces: Tag,
  sub_agents: Bot,
  browser_control: Monitor,
  computed_answers: Calculator,
  devops_cli: Terminal,
  control: ShieldCheck,
  usage_limits: Gauge,
  privacy: Lock,
  native_apps: TabletSmartphone,
  responsive: Smartphone,
  simplicity: MousePointerClick,
  themes: Palette,
  connected_services: Mail,
  environment: CloudSun,
  smart_home: Lightbulb,
  web_intelligence: Compass,
  voice_mode: Mic,
};
