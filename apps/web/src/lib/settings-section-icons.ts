/**
 * Section token → lucide icon, for surfaces that show a section without
 * mounting it (the master-detail rail, the overview cards).
 *
 * Each icon is the ONE the component itself passes to `<SettingsSection>` —
 * held to that by `__tests__/settings-section-icons.test.ts`, which reads the
 * identifier out of every component's source and resolves its lucide alias.
 * Completeness is the `Record` type: a new token fails to compile until it has
 * an icon here.
 */

import {
  Bell,
  Blocks,
  BookOpen,
  Brain,
  Bug,
  CalendarClock,
  Cpu,
  DollarSign,
  Eye,
  DownloadCloud,
  FileSpreadsheet,
  Fingerprint,
  Gauge,
  Globe,
  HeartPulse,
  Image as ImageIcon,
  Languages,
  LayoutDashboard,
  LayoutGrid,
  MapPin,
  Library,
  ListTodo,
  Megaphone,
  MessageCircle,
  Mic,
  MonitorSmartphone,
  Palette,
  PhoneCall,
  Plug,
  Puzzle,
  Sparkles,
  SlidersHorizontal,
  TerminalSquare,
  Type,
  Users,
  Vibrate,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { SettingsSectionToken } from './settings-sections';

export const SETTINGS_SECTION_ICONS: Readonly<Record<SettingsSectionToken, LucideIcon>> = {
  // ---- Preferences
  language: Languages,
  timezone: Globe,
  location: MapPin,
  theme: Palette,
  font: Type,
  'eyes-style': Eye,
  'display-mode': LayoutGrid,
  haptics: Vibrate,
  'briefing-grid': LayoutDashboard,
  'chat-shortcuts': TerminalSquare,
  notifications: Bell,
  channels: MessageCircle,
  'security-auth': Fingerprint,
  'security-devices': MonitorSmartphone,
  'security-export': DownloadCloud,
  'voice-mode': Mic,
  'image-generation': ImageIcon,
  connectors: Plug,
  'telephony-calls': PhoneCall,
  'admin-mcp-servers': Plug,
  'mcp-servers': Plug,
  'debug-panel': Bug,

  // ---- Features
  personality: Sparkles,
  psyche: Brain,
  memories: Brain,
  interests: Sparkles,
  'open-loops': ListTodo,
  habits: CalendarClock,
  'peer-connections': Users,
  heartbeat: Bell,
  'scheduled-actions': CalendarClock,
  journals: BookOpen,
  'health-metrics': HeartPulse,
  skills: Blocks,
  plugins: Puzzle,
  'rag-spaces': Library,
  'user-consumption-export': FileSpreadsheet,

  // ---- Administration
  'admin-users': Users,
  'admin-usage-limits': Gauge,
  'admin-consumption-export': FileSpreadsheet,
  'admin-broadcast': Megaphone,
  'admin-connectors': Plug,
  'admin-llm-pricing': DollarSign,
  'admin-google-api-pricing': Globe,
  'admin-image-pricing': ImageIcon,
  'admin-llm-config': Cpu,
  'admin-personalities': Sparkles,
  'admin-skills': Blocks,
  'rag-spaces-admin': Library,
  'admin-capabilities': SlidersHorizontal,
  'admin-public-demo-link': Globe,
  'debug-settings': Bug,
};
