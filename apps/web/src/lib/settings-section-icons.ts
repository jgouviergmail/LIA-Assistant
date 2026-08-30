/**
 * Section token → lucide icon, for surfaces that show a section without
 * mounting it (the master-detail rail, the overview cards).
 *
 * Each icon is the ONE the component itself passes to `<SettingsSection>` —
 * held to that by `__tests__/settings-section-icons.test.ts`, which reads the
 * identifier out of every component's source and resolves its lucide alias.
 * Completeness is the `Record` type: a new token fails to compile until it has
 * an icon here.
 *
 * Every section carries its OWN glyph, with exactly one deliberate exception:
 * `user-consumption-export` and `admin-consumption-export` share
 * `FileSpreadsheet`, because they share one component that branches on `mode`.
 * Giving them separate glyphs would mean writing `icon={MAP[mode]}`, which the
 * registry test cannot read — and that test's "exactly one icon per file" rule
 * is worth more than the distinction: the two live in different tabs and never
 * appear on screen together.
 *
 * The other eleven shared glyphs were resolved in the same pass. `Plug` covered
 * four sections; colour cannot separate a repeated shape, so the shape had to
 * change.
 */

import {
  Activity,
  Bell,
  Blocks,
  BookOpen,
  BookUser,
  Boxes,
  Brain,
  Bug,
  Cable,
  CalendarClock,
  Coins,
  Compass,
  Cpu,
  DollarSign,
  DownloadCloud,
  Drama,
  Eye,
  FileSpreadsheet,
  Fingerprint,
  Gauge,
  Globe,
  Handshake,
  HeartPulse,
  Image as ImageIcon,
  Languages,
  LayoutDashboard,
  LayoutGrid,
  Library,
  LibraryBig,
  ListTodo,
  MapPin,
  Megaphone,
  MessageCircle,
  Mic,
  Microscope,
  MonitorSmartphone,
  Palette,
  PhoneCall,
  Plug,
  Puzzle,
  Radar,
  Receipt,
  Repeat,
  Server,
  ServerCog,
  Signpost,
  SlidersHorizontal,
  Sparkles,
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
  'admin-mcp-servers': ServerCog,
  'mcp-servers': Server,
  'debug-panel': Bug,

  // ---- Features
  personality: Sparkles,
  psyche: Brain,
  memories: BookUser,
  interests: Compass,
  'open-loops': ListTodo,
  habits: Repeat,
  'peer-connections': Handshake,
  heartbeat: Radar,
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
  'admin-connectors': Cable,
  'admin-llm-pricing': DollarSign,
  'admin-google-api-pricing': Coins,
  'admin-image-pricing': Receipt,
  'admin-llm-config': Cpu,
  'admin-personalities': Drama,
  'admin-skills': Boxes,
  'rag-spaces-admin': LibraryBig,
  'admin-capabilities': SlidersHorizontal,
  'admin-diagnostics': Activity,
  'admin-public-demo-link': Signpost,
  'debug-settings': Microscope,
};
