/**
 * FAQ section registry shared by the dashboard FAQ (FAQContent) and the
 * public landing FAQ page: one icon per section plus the ordered subset of
 * sections exposed to signed-out visitors.
 */

import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  Bell,
  Blocks,
  BookOpen,
  Bot,
  CalendarClock,
  Cloud,
  FileOutput,
  Gauge,
  Globe,
  Handshake,
  HeartPulse,
  HelpCircle,
  ImageIcon,
  Library,
  Mail,
  MessageSquare,
  Mic,
  PhoneCall,
  Plug,
  Settings,
  Shield,
  Sparkles,
  Users,
  Zap,
} from 'lucide-react';

/** Icon per FAQ section key (`faq.sections.<key>` in the locale files). */
export const FAQ_SECTION_ICONS: Record<string, LucideIcon> = {
  getting_started: Zap,
  chat: MessageSquare,
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
  sub_agents: Bot,
  rag_spaces: Library,
  voice_mode: Mic,
  image_generation: ImageIcon,
  document_generation: FileOutput,
  journals: BookOpen,
  health_metrics: HeartPulse,
  usage_limits: Gauge,
  privacy: Shield,
  other: HelpCircle,
};

/**
 * FAQ sections shown to signed-out visitors on /faq, in display order.
 *
 * Selection rationale: the questions a prospect asks BEFORE creating an
 * account — what LIA is (getting_started), which services it plugs into
 * (connectors), its boldest differentiators (telephony, voice_mode,
 * image_generation) and the trust base (privacy). App-operation sections
 * (settings, usage limits, journals…) stay behind login where they make sense.
 */
export const PUBLIC_FAQ_SECTIONS = [
  'getting_started',
  'connectors',
  'telephony',
  'voice_mode',
  'image_generation',
  'privacy',
] as const;

export type PublicFaqSection = (typeof PUBLIC_FAQ_SECTIONS)[number];
