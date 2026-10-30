import {
  Activity,
  ArrowRightLeft,
  BadgeCheck,
  BarChart3,
  Bell,
  Brain,
  ClipboardCheck,
  Compass,
  Cpu,
  Eye,
  Flag,
  FolderTree,
  GitBranch,
  Globe,
  Heart,
  Lightbulb,
  Mic,
  MousePointerClick,
  Plug,
  Puzzle,
  Scale,
  Shield,
  Sparkles,
  TabletSmartphone,
  UserCheck,
  Users,
  Zap,
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
  { id: 'ddd', icon: FolderTree },
  { id: 'pipeline', icon: ArrowRightLeft },
  { id: 'hitl', icon: UserCheck },
  { id: 'memory', icon: Brain },
  { id: 'llm', icon: Cpu },
  { id: 'connectors', icon: Plug },
  { id: 'voice', icon: Mic },
  { id: 'proactivity', icon: Bell },
  { id: 'security', icon: Shield },
  { id: 'observability', icon: BarChart3 },
  { id: 'interfaces', icon: TabletSmartphone },
  { id: 'engineering', icon: GitBranch },
  { id: 'conclusion', icon: Flag },
] as const;

export const WHY_TOC_SECTIONS: readonly GuideTocSection[] = [
  { id: 'context', icon: Globe },
  { id: 'capabilities', icon: Zap },
  { id: 'family_server', icon: Users },
  { id: 'simple_admin', icon: MousePointerClick },
  { id: 'transparency', icon: Eye },
  { id: 'emotional_depth', icon: Heart },
  { id: 'control', icon: UserCheck },
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
