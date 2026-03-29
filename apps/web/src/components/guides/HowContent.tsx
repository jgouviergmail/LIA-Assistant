import fs from 'fs';
import path from 'path';
import {
  Compass,
  Blocks,
  FolderTree,
  Network,
  ArrowRightLeft,
  ClipboardList,
  Sparkles,
  Target,
  UserCheck,
  Database,
  Brain,
  Cpu,
  Plug,
  Cable,
  Mic,
  Bell,
  BookOpen,
  Globe,
  Shield,
  BarChart3,
  Gauge,
  GitBranch,
  Layers,
  FileText,
  Rocket,
} from 'lucide-react';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from './GuideMarkdown';
import { GuideToc } from './GuideLayout';

interface HowContentProps {
  lng: string;
}

const TOC_SECTIONS = [
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
] as const;

function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `how.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'how.fr.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function HowContent({ lng }: HowContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`how.toc.${id}`),
    icon,
  }));

  const sectionIds = TOC_SECTIONS.map(s => s.id);
  const sectionIcons = TOC_SECTIONS.map(s => s.icon);
  const content = loadGuideContent(lng);

  return (
    <article className="max-w-3xl mx-auto">
      <GuideToc items={tocItems} />
      <GuideMarkdown content={content} sectionIds={sectionIds} sectionIcons={sectionIcons} />
    </article>
  );
}
