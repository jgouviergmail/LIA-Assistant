/**
 * Single source of truth for the editorial landing narrative (chapters 01-05
 * plus the basics band). Every detailed feature card of the former features
 * wall is re-parented here — never deleted — and rendered inside the
 * per-chapter expandable catalogs, reusing the existing translated
 * `landing.features.<key>.{title,description}` copy in all 6 locales.
 *
 * ANTI-REGRESSION CONTRACT: `REQUIRED_FEATURE_KEYS` is the canonical
 * inventory of detailed feature cards. The guard test
 * `__tests__/editorial-content-coverage.test.ts` asserts that the chapter
 * catalogs plus the basics catalog cover it exactly (no loss, no duplicate).
 * Removing a feature from the landing therefore requires a deliberate edit
 * of the contract, never an accidental omission.
 */

import type { LucideIcon } from 'lucide-react';
import {
  CloudSun,
  Activity,
  AppWindow,
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
} from 'lucide-react';

export type ChapterId = 'act' | 'know' | 'anticipate' | 'control' | 'grow' | 'connect';

export interface ChapterConfig {
  id: ChapterId;
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
    key: 'c1',
    anchor: 'chapter-act',
    num: '01',
    mood: '😏',
    benefits: 4,
    catalog: [
      'natural_language',
      'multi_agent',
      'computed_answers',
      'telephony',
      'browser_control',
      'smart_home',
      'image_generation',
      'document_generation',
      'excalidraw',
      'rich_responses',
    ],
    tinted: false,
  },
  {
    id: 'know',
    key: 'c2',
    anchor: 'chapter-know',
    num: '02',
    mood: '🙂',
    benefits: 3,
    catalog: [
      'memory',
      'personal_crm',
      'briefing',
      'personalities',
      'psyche',
      'journals',
      'self_knowledge',
    ],
    tinted: true,
  },
  {
    id: 'anticipate',
    key: 'c3',
    anchor: 'chapter-anticipate',
    num: '03',
    mood: '😏',
    benefits: 3,
    catalog: ['proactive', 'interests', 'habits', 'reminders_scheduling', 'health_metrics'],
    tinted: false,
  },
  {
    id: 'control',
    key: 'c4',
    anchor: 'chapter-control',
    num: '04',
    mood: '🙂',
    benefits: 4,
    catalog: ['control', 'usage_limits', 'privacy', 'native_apps'],
    tinted: true,
  },
  {
    id: 'grow',
    key: 'c5',
    anchor: 'chapter-grow',
    num: '05',
    mood: '😏',
    benefits: 3,
    catalog: ['skills', 'plugins', 'mcp', 'mcp_apps', 'rag_spaces', 'sub_agents', 'devops_cli'],
    tinted: false,
  },
  {
    id: 'connect',
    key: 'c6',
    anchor: 'chapter-connect',
    num: '06',
    mood: '🙂',
    benefits: 3,
    catalog: ['peers'],
    tinted: true,
  },
] as const;

/** Commodity cards living in the basics band's own catalog. */
export const BASICS_CATALOG: readonly string[] = [
  'connected_services',
  'environment',
  'web_intelligence',
  'voice_mode',
  'languages',
  'multichannel',
  'attachments',
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
  'multichannel',
  'languages',
  // personality & memory
  'memory',
  'personal_crm',
  'peers',
  'personalities',
  'psyche',
  'self_knowledge',
  'journals',
  // proactivity & automation
  'briefing',
  'proactive',
  'interests',
  'habits',
  'reminders_scheduling',
  'telephony',
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
  multichannel: MessageCircle,
  languages: Globe,
  memory: Brain,
  personal_crm: Users,
  peers: Handshake,
  personalities: Smile,
  psyche: Heart,
  self_knowledge: HelpCircle,
  journals: BookOpen,
  briefing: Sunrise,
  proactive: BellRing,
  interests: Star,
  habits: Repeat,
  reminders_scheduling: CalendarClock,
  telephony: PhoneCall,
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
