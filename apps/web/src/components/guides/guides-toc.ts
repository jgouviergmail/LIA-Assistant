import {
  Activity,
  ArrowRightLeft,
  BadgeCheck,
  BarChart3,
  Bell,
  Blocks,
  BookOpen,
  Brain,
  Cable,
  Calculator,
  ClipboardCheck,
  ClipboardList,
  Compass,
  Cpu,
  Database,
  Eye,
  FileText,
  FileSpreadsheet,
  FolderTree,
  Gauge,
  GitBranch,
  Globe,
  Heart,
  HeartPulse,
  Layers,
  Lightbulb,
  Mic,
  MousePointerClick,
  Network,
  Palette,
  Plug,
  Puzzle,
  Rocket,
  SlidersHorizontal,
  Scale,
  Shield,
  Smile,
  Sparkles,
  Target,
  UserCheck,
  Users,
  Waves,
  Zap,
  CalendarClock,
  Stethoscope,
  TabletSmartphone,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/**
 * Navigation spine of the three showcase guides.
 *
 * `GuideMarkdown` STRIPS the markdown table of contents (everything before the
 * first `## 1.`) and assigns anchor ids to `<h2>` elements **positionally**:
 * the Nth heading gets `sectionIds[N]`. So these arrays — not the ToC written in
 * the `.md` — are what the in-app sidebar navigates, and an array shorter than
 * the document leaves its trailing sections with `id={undefined}`, unreachable
 * and iconless, in all six languages at once.
 *
 * That is exactly what happened: `how` carried 25 entries for 26 sections, so
 * §26 (Psyche Engine) was unnavigable from the day it was written. Extracted
 * here out of the three server components so a test can compare each array
 * against the headings actually present in the six markdown files —
 * `__tests__/guides-structure.test.ts`.
 *
 * Every `id` must have an i18n label under `{family}.toc.{id}` in the six
 * locales; the label is what the sidebar renders.
 */
export interface GuideTocSection {
  readonly id: string;
  readonly icon: LucideIcon;
}

export const HOW_TOC_SECTIONS: readonly GuideTocSection[] = [
  { id: 'context', icon: Compass },
  { id: 'stack', icon: Blocks },
  { id: 'ddd', icon: FolderTree },
  { id: 'langgraph', icon: Network },
  { id: 'pipeline', icon: ArrowRightLeft },
  { id: 'planning', icon: ClipboardList },
  { id: 'smart_services', icon: Sparkles },
  { id: 'semantic', icon: Target },
  { id: 'hitl', icon: UserCheck },
  { id: 'state', icon: Database },
  { id: 'memory', icon: Brain },
  { id: 'llm', icon: Cpu },
  { id: 'connectors', icon: Plug },
  { id: 'mcp', icon: Cable },
  { id: 'voice', icon: Mic },
  { id: 'proactivity', icon: Bell },
  { id: 'rag', icon: BookOpen },
  { id: 'browser', icon: Globe },
  { id: 'security', icon: Shield },
  { id: 'observability', icon: BarChart3 },
  { id: 'performance', icon: Gauge },
  { id: 'cicd', icon: GitBranch },
  { id: 'patterns', icon: Layers },
  { id: 'adr', icon: FileText },
  { id: 'extensibility', icon: Rocket },
  { id: 'psyche', icon: HeartPulse },
  { id: 'habits', icon: CalendarClock },
  { id: 'governance', icon: SlidersHorizontal },
  { id: 'tabular_admin', icon: FileSpreadsheet },
  { id: 'evolution', icon: Eye },
  { id: 'expressive_eyes', icon: Smile },
  { id: 'native_apps', icon: TabletSmartphone },
  { id: 'self_diagnostics', icon: Stethoscope },
  { id: 'computed_answers', icon: Calculator },
  { id: 'measured_palette', icon: Palette },
  { id: 'declared_register', icon: Smile },
  { id: 'shock_absorbers', icon: Waves },
  { id: 'meetings', icon: ClipboardList },
] as const;

export const WHY_TOC_SECTIONS: readonly GuideTocSection[] = [
  { id: 'context', icon: Globe },
  { id: 'simple_admin', icon: MousePointerClick },
  { id: 'capabilities', icon: Zap },
  { id: 'family_server', icon: Users },
  { id: 'sovereignty', icon: Shield },
  { id: 'transparency', icon: Eye },
  { id: 'emotional_depth', icon: Heart },
  { id: 'reliability', icon: Activity },
  { id: 'openness', icon: Puzzle },
  { id: 'vision', icon: Compass },
] as const;

export const STORY_TOC_SECTIONS: readonly GuideTocSection[] = [
  { id: 'essentials', icon: Sparkles },
  { id: 'approach', icon: Compass },
  { id: 'method', icon: ClipboardCheck },
  { id: 'tradeoffs', icon: Scale },
  { id: 'operations', icon: Activity },
  { id: 'proof', icon: BadgeCheck },
  { id: 'convictions', icon: Lightbulb },
] as const;
