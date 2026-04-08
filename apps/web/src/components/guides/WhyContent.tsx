import fs from 'fs';
import path from 'path';
import {
  Globe,
  MousePointerClick,
  Zap,
  Users,
  Shield,
  Eye,
  Heart,
  Activity,
  Puzzle,
  Compass,
} from 'lucide-react';
import { initI18next } from '@/i18n';
import { GuideMarkdown } from './GuideMarkdown';
import { GuideToc } from './GuideLayout';

interface WhyContentProps {
  lng: string;
}

const TOC_SECTIONS = [
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

function loadGuideContent(lng: string): string {
  const guidesDir = path.join(process.cwd(), 'src', 'data', 'guides');
  const localizedPath = path.join(guidesDir, `why.${lng}.md`);
  const fallbackPath = path.join(guidesDir, 'why.fr.md');

  try {
    return fs.readFileSync(fs.existsSync(localizedPath) ? localizedPath : fallbackPath, 'utf-8');
  } catch {
    return '';
  }
}

export async function WhyContent({ lng }: WhyContentProps) {
  const { t } = await initI18next(lng);

  const tocItems = TOC_SECTIONS.map(({ id, icon }) => ({
    id,
    label: t(`why.toc.${id}`),
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
