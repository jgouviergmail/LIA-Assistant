/**
 * FAQ section registry shared by the dashboard FAQ (FAQContent) and the
 * public landing FAQ page: the display order, one icon per section, and the
 * ordered subset of sections exposed to signed-out visitors.
 *
 * Every `faq.sections.<key>` of the locale files must be listed in
 * `FAQ_SECTIONS` and carry an icon: a section translated in six languages but
 * absent from this list renders nowhere (`__tests__/section-registry.test.ts`).
 */

import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  Bell,
  Blocks,
  Brain,
  Calculator,
  BookOpen,
  Bot,
  CalendarClock,
  Cloud,
  FileOutput,
  FolderOpen,
  Gauge,
  Globe,
  Handshake,
  HeartPulse,
  HelpCircle,
  ImageIcon,
  Library,
  Mail,
  Map,
  MessageSquare,
  Mic,
  Package,
  PhoneCall,
  Plug,
  Radio,
  Repeat,
  ScrollText,
  Send,
  Server,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Sunrise,
  Users,
  Zap,
  ClipboardList,
  SquareKanban,
} from 'lucide-react';

/** Icon per FAQ section key (`faq.sections.<key>` in the locale files). */
export const FAQ_SECTION_ICONS: Record<string, LucideIcon> = {
  getting_started: Zap,
  chat: MessageSquare,
  world: Map,
  settings: Settings,
  connectors: Globe,
  telephony: PhoneCall,
  peers: Handshake,
  relations: Users,
  tool_examples_services: Mail,
  tool_examples_external: Cloud,
  rappels: Bell,
  interests: Sparkles,
  heartbeat: Activity,
  scheduled_actions: CalendarClock,
  mcp_servers: Plug,
  skills: Blocks,
  plugins: Package,
  sub_agents: Bot,
  rag_spaces: Library,
  meetings: ClipboardList,
  workboard: SquareKanban,
  voice_mode: Mic,
  image_generation: ImageIcon,
  document_generation: FileOutput,
  journals: BookOpen,
  health_metrics: HeartPulse,
  usage_limits: Gauge,
  privacy: Shield,
  other: HelpCircle,
  today: Sunrise,
  telegram: Send,
  computed: Calculator,
  habits: Repeat,
  files: FolderOpen,
  radio: Radio,
  psyche: Brain,
  registers: ScrollText,
  administration: SlidersHorizontal,
  self_hosting: Server,
};

/** Every FAQ section, in display order (the dashboard FAQ renders this list). */
export const FAQ_SECTIONS = [
  'getting_started',
  'today',
  'chat',
  'world',
  'settings',
  'connectors',
  'telephony',
  'telegram',
  'peers',
  'relations',
  'tool_examples_services',
  'tool_examples_external',
  'computed',
  'rappels',
  'interests',
  'heartbeat',
  'habits',
  'scheduled_actions',
  'workboard',
  'mcp_servers',
  'skills',
  'plugins',
  'sub_agents',
  'rag_spaces',
  'files',
  'voice_mode',
  'radio',
  'meetings',
  'image_generation',
  'document_generation',
  'journals',
  'psyche',
  'health_metrics',
  'usage_limits',
  'privacy',
  'registers',
  'administration',
  'self_hosting',
  'other',
] as const;

/**
 * FAQ sections shown to signed-out visitors on /faq, in display order.
 *
 * Selection rationale: the questions a prospect asks BEFORE creating an
 * account — what LIA is (getting_started), its shared world (world), which
 * services it plugs into (connectors), its boldest differentiators (telephony, voice_mode, radio,
 * image_generation), the trust base (privacy, registers) and how to run it
 * yourself (self_hosting). App-operation sections (settings, usage limits,
 * journals…) stay behind login where they make sense.
 */
export const PUBLIC_FAQ_SECTIONS = [
  'getting_started',
  'world',
  'connectors',
  'telephony',
  'voice_mode',
  'radio',
  'image_generation',
  'privacy',
  'registers',
  'self_hosting',
] as const;

export type PublicFaqSection = (typeof PUBLIC_FAQ_SECTIONS)[number];
